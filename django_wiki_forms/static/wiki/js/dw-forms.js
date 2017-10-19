$.ajaxSetup({
  beforeSend: function(xhr, settings) {
    if (settings.type == 'POST' && !this.crossDomain) {
      csrftoken = document.cookie.replace(/^(.*;)?\s*csrftoken=(\w+?)(;.*)?/, '$2');
      xhr.setRequestHeader("X-CSRFToken", csrftoken);
    }
  }
})


function wiki_input_get_data(field, fn) {
  $.ajax({
         url: "/" + ARTICLE_ID + "/plugin/forms/input/" + field.attr("data-id"),
         type: 'GET',
         contentType: "application/json",
         success: fn,
         error: function(data){
           $('.notification-cnt').html("<b>!</b>");
         },
  });
}

function wiki_input_post_data(field, val) {
  console.log('postdata: ' + val);
  $.ajax({
         url: "/" + ARTICLE_ID + "/plugin/forms/input/" + field.attr("data-id"),
         type: 'POST',
         data: JSON.stringify(val),
         contentType: "application/json",
         error: function(data){
           $('.notification-cnt').html("<b>!</b>");
         },
  });
}


function wiki_display_data(field) {
  console.log('displaydata: ');
  $.ajax({
         url: "/" + ARTICLE_ID + "/plugin/forms/display/" + field.attr("data-id"),
         type: 'GET',
         contentType: "text/html",
         success: function(data){
           field.html(data);
         },
         error: function(data){
           $('.notification-cnt').html("<b>!</b>");
         },
  });
}


function receiveMessage(msg) {
  console.log('Message from Websocket: ' + msg);
  var m = msg.split(':');

  $('span[data-listen].dw-forms').each(function(n,e) {
    $(e).attr('data-listen').split(",").some(function(i) {
      var l = i.split(':');
      if ((l[0] != m[0] || (l[0] == -1 && ARTICLE_ID == m[0])) &&
          l[1] != m[1] && 
          (l[2] == '' || m[2] == USER_ID)) {
        wiki_display_data($(e));
        return true;
      } else {
        return false;
      }
    })
  })
}


function update_later(fn) {
  var timer = null;

  return function () {
    var context = this, args = arguments;
    clearTimeout(timer);
    timer = setTimeout(function () {
      fn.apply(context, args);
    }, 2000);
  };
}


$(document).ready(function() {
  var ws4redis = WS4Redis({
                          uri: WEBSOCKET_URI + 'django-wiki-forms?subscribe-broadcast',
                          receive_message: receiveMessage,
                          heartbeat_msg: WS4REDIS_HEARTBEAT
  });

  $('input[type=file][data-id].dw-input').change(function(ev) {
    var n = ev.target.files.length;
    var data = [];

    for (var i = 0; i < n; i++) {
      var reader = new FileReader();
      reader._file = ev.target.files[i];

      reader.onload = function(ev2) {
        data.push({
          name: ev2.target._file.name,
          size: ev2.target._file.size,
          type: ev2.target._file.type,
          content: ev2.target.result
        });

        if (data.length == n) {
          wiki_input_post_data($(ev.target), data);
        }
      }
      reader.readAsBinaryString(reader._file);
    }
  })


  $('input[type!=file][data-id].dw-input').change(function() {
    wiki_input_post_data($(this), $(this).val());
  })

  $('textarea[data-id].dw-input').change(function() {
    wiki_input_post_data($(this), $(this).val());
  })

  $('input[type!=file][data-id].dw-input').keyup(update_later(function(){
    wiki_input_post_data($(this), $(this).val());
  }))




  $('span[data-id].dw-forms').each(function() {
    wiki_display_data($(this));
  });

  $('input[type=file][data-id].dw-input').each(function(i,e) {
    wiki_input_get_data($(e), function(data){
      if (!data.locked) {
        $(e).prop('disabled', false);
      }
    })
  })

  $('input[type!=file][data-id].dw-input').each(function(i,e) {
    wiki_input_get_data($(e), function(data){
      $(e).val(data.val);

      if (!data.locked) {
        $(e).prop('disabled', false);
      }
    })
  })

  $('textarea[data-id].dw-input').each(function(i,e) {
    wiki_input_get_data($(e), function(data){
      $(e).val(data.val);

      if (!data.locked) {
        $(e).prop('disabled', false);
      }
    })
  })

})
