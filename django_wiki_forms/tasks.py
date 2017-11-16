from __future__ import absolute_import, unicode_literals

from celery import shared_task
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model

import magic
import docker
import docker.tls
import docker.errors
import io
import re
import json
import tarfile
import os

from . import models
from . import utils

import ipdb  # NOQA

logger = get_task_logger(__name__)
mime = magic.Magic(mime=True)


@shared_task
def evaluate_idef(idef_pk, owner_pk):
    try:
        idef = models.InputDefinition.objects.get(pk=idef_pk)
    except models.InputDefinition.DoesNotExist:
        logger.warning("evaluate of unknown idef {}".format(idef_pk))
        return

    owner = get_user_model().objects.get(pk=owner_pk)
    logger.warning("evaluate {} (@{})".format(idef, owner))
    utils.evaluate_idef(idef, owner)



def docker_api():
    return docker.APIClient(base_url='unix://var/run/docker.sock')
    # tls = docker.tls.TLSConfig(ca_cert=os.path.expanduser("~/.docker/ca.pem"),
    #        client_cert=(os.path.expanduser("~/.docker/cert.pem"), os.path.expanduser("~/.docker/key.pem")), verify=True)
    # return docker.APIClient(base_url=settings.DOCKER_BASE_URL, tls=tls)


def docker_add_file(tar, name, content):
    if content is None:
        return

    ti = tarfile.TarInfo(name=name)
    ti.size = len(content)
    tar.addfile(ti, io.BytesIO(content))


re_ansi_escape = re.compile(r'\x1b[^m]*m')
re_stepx = re.compile("^Step\s+(\d+)[/\d]*\s+:\s?(.*)$")
re_docker_comment = re.compile("^ ---> (.*)$")
re_docker_comment_image = re.compile("^ ---> ([0-9a-z]{12})$")
re_docker_image = re.compile("^\s*Successfully built (\S+)\s*$")


@shared_task
def remove_image(img):
    api = docker_api()
    api.remove_image(img, force=True)


def create_image(api, image, scenario, args):  # NOQA
    img = io.BytesIO()
    tar = tarfile.TarFile(fileobj=img, mode="w")

    dfile = "FROM {}\n".format(image)

    dfile += "COPY scenario /data/scenario\n"
    dfile += "RUN chmod a+x /data/scenario\n"
    docker_add_file(tar, 'scenario', scenario.encode('utf-8'))

    for n, arg in enumerate(args if args else list()):
        if type(arg) == list and len(arg) > 0 and 'content' in arg[0]:
            for m, f in enumerate(arg):
                dfile += "COPY {}.{} /data/arg{}/{}\n".format(n, m, n, f['name'])
                docker_add_file(tar, "{}.{}".format(n, m), f['content'].encode('utf-8'))
        else:
            dfile += "COPY {} /data/arg{}/json\n".format(n, n)
            docker_add_file(tar, '{}'.format(n), json.dumps(arg).encode('utf-8'))

    dfile += "RUN mkdir -p /data/out\n"

    docker_add_file(tar, 'Dockerfile', dfile.encode('utf-8'))

    tar.close()
    img.seek(0)

    image_id = None
    err = None
    try:
        for line in api.build(fileobj=img, rm=True, custom_context=True):
            out = json.loads(line.decode('utf8'))

            if 'stream' in out:
                st = re_ansi_escape.sub('', out['stream'])
                logger.debug("docker: {}".format(out['stream']))

                m = re_docker_comment_image.match(st)
                if m:
                    # remove_image.apply_async(args=[m.group(1)], kwargs={}, countdown=10)
                    continue

                m = re_docker_image.match(st)
                if m:
                    image_id = m.group(1)
                    continue

            elif 'errorDetail' in out:
                err = out['error']

    except docker.errors.APIError as ex:
        logger.error("docker run failed:  {}".format(ex.explanation))
        return

    if err is not None:
        logger.error("docker run failed: {}".format(err))
        return

    if not image_id:
        logger.error("docker run failed: ?!?!")
        return

    return image_id


@shared_task
def update_docker(idk_pk, countdown):
    try:
        idk = models.InputDocker.objects.get(pk=idk_pk)
    except models.InputDefinition.DoesNotExist:
        logger.warning("update_docker: unknown id {}".format(idk_pk))
        return

    api = docker_api()

    cid = idk.container_id
    out = api.logs(cid).decode('utf-8'),
    info = api.inspect_container(cid)

    data = {'type': 'docker', 'out': out}

    if countdown > 0 and info['State']['Running']:
        data['running'] = True

        utils.update_idv(idk.value, data)
        update_docker.apply_async(args=[idk_pk, countdown-1], kwargs={}, countdown=3)

        return

    if info['State']['Running']:
        api.kill(cid)

    api.wait(cid)
    (t, s) = api.get_archive(cid, "/data/out/")
    info = api.inspect_container(cid)

    data['running'] = False
    data['exitcode'] = info['State']['ExitCode']
    data['data'] = list()

    tar = tarfile.open(fileobj=io.BytesIO(t.data), mode="r")

    for m in tar.getmembers():
        if not m.isfile():
            continue

        content = tar.extractfile(m).read()
        data['data'].append({
            'name': os.path.relpath(m.name, 'out'),
            'size': m.size,
            'content': content.decode('utf-8'),
            'type': mime.from_buffer(content)})

    utils.update_idv(idk.value, data)

    api.remove_container(cid)
    idk.delete()


@shared_task
def run_docker(docker_pk):
    try:
        idk = models.InputDocker.objects.get(pk=docker_pk)
    except models.InputDefinition.DoesNotExist:
        logger.warning("run_docker: unknown id {}".format(docker_pk))
        return

    api = docker_api()

    image_id = create_image(api, idk.image, idk.scenario, json.loads(idk.args))
    if not image_id:
        idk.delete()

    idk.container_id = api.create_container(image=image_id, command="/data/scenario")['Id']
    idk.save()

    logger.info("start container {}".format(idk.container_id))
    api.start(idk.container_id)

    update_docker.apply_async(args=[idk.pk, 10], kwargs={}, countdown=1)

    return idk
