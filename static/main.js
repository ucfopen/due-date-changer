$(document).ready(function() {

    // resize containing iframe height
    function resizeFrame(){
        console.log("resizing frame...");
        var default_height = $('body').height() + 50;
        default_height = default_height > 500 ? default_height : 500;

        // IE 8 & 9 only support string data, so send objects as string
        parent.postMessage(JSON.stringify({
          subject: "lti.frameResize",
          height: default_height
        }), "*");
    }

    // update iframe height on resize
    $(window).on('resize', function(){
        resizeFrame();
    });

    resizeFrame();

});
