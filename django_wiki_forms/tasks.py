from __future__ import absolute_import, unicode_literals

from celery import shared_task
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model

import docker
import docker.tls
import docker.errors
import tarfile
import io
import re
import json

from . import models
from . import utils


User = get_user_model()
logger = get_task_logger(__name__)
# mime = magic.Magic(mime=True)


@shared_task
def evaluate_idef(idef_pk, owner_pk):
    try:
        idef = models.InputDefinition.objects.get(pk=idef_pk)
    except models.InputDefinition.DoesNotExist:
        logger.warning("evaluate of unknown idef {}".format(idef_pk))
        return

    owner = User.objects.get(pk=owner_pk)
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


def create_container(img):
    api = docker_api()
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
                    remove_image.apply_async(args=[m.group(1)], kwargs={}, countdown=10)
                    continue

                m = re_docker_image.match(st)
                if m:
                    image_id = m.group(1)
                    continue

            elif 'errorDetail' in out:
                err = out['error']

        if err is not None:
            logger.error("docker run failed: {}".format(err))
            return

        if image_id:
            return api.create_container(image_id)

        logger.error("docker run failed: ?!?!")
    except docker.errors.APIError as ex:
        logger.error("docker run failed:  {}".format(ex.explanation))



@shared_task
def update_docker(docker_pk):
    try:
        idk = models.InputDocker.objects.get(pk=docker_pk)
    except models.InputDefinition.DoesNotExist:
        logger.warning("update_docker: unknown id {}".format(docker_pk))
        return

    api = docker_api()
    out = json.loads(api.inspect_containter(idk.container_id))
    print(out)


@shared_task
def run_docker(docker_pk):
    try:
        idk = models.InputDocker.objects.get(pk=docker_pk)
    except models.InputDefinition.DoesNotExist:
        logger.warning("run_docker: unknown id {}".format(docker_pk))
        return

    img = io.BytesIO()
    tar = tarfile.TarFile(fileobj=img, mode="w")

    dfile = "FROM {}\n".format(idk.image)
    dfile += "COPY scenario /data/scenario\n"
    dfile += "ENTRYPOINT [ '/cenario' ]\n"
    docker_add_file(tar, 'scenario', idk.scenario.encode('utf-8'))

    if idk.args is not None:
        dfile += "COPY args /data/args\n"
        docker_add_file(tar, 'args', idk.args.encode('utf-8'))

    docker_add_file(tar, 'Dockerfile', dfile.encode('utf-8'))

    tar.close()
    img.seek(0)

    # with open("/tmp/aaa.tar",'wb') as out:
    #    out.write(img.read())
    #    img.seek(0)

    container_id = create_container(img)

    if container_id:
        idk.containerId = container_id
        idk.save()

        update_docker.apply_async(args=[docker_pk], kwargs={}, countdown=1)
    else:
        idk.delete()
