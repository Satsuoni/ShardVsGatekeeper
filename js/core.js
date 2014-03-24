// JavaScript Document
var chatInterval;
var colors={
	black:"000000",
	green:"00ff00",
	blue:"0000ff",
	red:"ff0000"
	};
var currentColor="000000";
var currentPM='';
var currentThreatID='';
function countNum(obj)
{
	var cnt=0;
	for (var i in obj) {
   if (obj.hasOwnProperty(i)) cnt++;
}
	return cnt;
}
function sendAjax(act,parameters)
{
	dat={action:act};
	for (var attrname in parameters) dat[attrname]=parameters[attrname];
	$.ajax({
		url:'/ajax',
		type :'POST',
		data: dat
		});
}
 function chatHtmlFromMsg(msg)
 {
	 if(msg.type==0)
	 return "<p style='color:#"+msg.color+";'>"+msg.time+"["+msg.name+"]"+" "+msg.text+"</p>"
	 else 
	 if(msg.type==1)
	 {
		  return "<p style='color:#"+msg.color+";'>"+msg.time+"[**SYSTEM**]"+" "+msg.text+"</p>"
	 }
 }
 
 onMessage = function(m) {
	// alert(m.data);
       msg = $.parseJSON(m.data);
		if(msg.kind=="ping")
		{
			//alert("Ping");
				$.ajax({
		url:'/ajax',
		data:{action:'putmeback'}
		});
		}
		if(msg.kind=="updatestate")
		{
			$("#playertype").html(msg.ptype);
			$("#playerkind").html(msg.pkind);
			$("#maintimer").html(msg.stimer);
			$("#shardpower").html(msg.shardpower);
			$("#gscore").html(msg.gscore);
			$("#sscore").html(msg.sscore);
			//alert(msg.stimer);
		}
  if(msg.kind=="updatechat")
  {   
   //alert(m.data);
	  ch=$("#chatbox").html();
	  txtstr=chatHtmlFromMsg(msg);
	  ch=ch+txtstr;
	  $("#chatbox").html(ch);
	   var newscrollHeight = $("#chatbox").prop("scrollHeight") - 20;
	  $("#chatbox").animate({ scrollTop: newscrollHeight }, 'normal');
  }
    if(msg.kind=="updatethreat")
  { 
  $("#disaster").html(msg.blocks)
  if(currentThreatID!='')
  {
  $("#disaster").find("input.threatid").filter("[value='"+currentThreatID+"']").parent().parent().css({"border-style":"solid", "border-width":"2px","border-color":"#f00"});
  }
  }
  if(msg.kind=="updateusers")
  {
	  getUserData();
  }
   if(msg.kind=="gotoSession")
   {
	   window.location.href="/session";
   }
     if(msg.kind=="gotoChat")
   {
	   window.location.href="/";
   }
 // 
 }
 
onOpened = function() {
	// alert('open');
	//alert("Ping");
				$.ajax({
		url:'/ajax',
		type :'POST',
		data:{action:'opened'}
		});
  //sendAjax('opened');
  getUserData();
};

onError=  function() {
  negotiate();
};
onClose=  function() {
  alert('Closed');
};

function getUserData()
{
		$.ajax({
		url:'/ajax',
		data:{action:'getuserlist'}
		}).done(function(data){
			$("#sidebar").html(data);
		});

}

function refreshChatbox()
{
		$.ajax({
		url:'/ajax',
		data:{action:'refreshchat'}
		}).done(function(data){
			ch=''
			mdat = $.parseJSON(data);
           var arrayLength = mdat.length;
;
			for(i=arrayLength-1;i>=0;i--)
			{
				msg=mdat[i];
			txtstr=chatHtmlFromMsg(msg);
	  ch=ch+txtstr;
			}
	  $("#chatbox").html(ch);
	  var newscrollHeight = $("#chatbox").prop("scrollHeight") - 20;
	  //alert(newscrollHeight);
	  //$("#chatbox").animate({ scrollTop: $('#chatbox')[0].scrollHeight}, 1000);
	  $("#chatbox").animate({ scrollTop: newscrollHeight }, 'normal');
		});

}
function negotiate()
{
	window.chid=''
	  $.ajax({
		url:'/ajax',
		data:{action:'negotiate'}
		}).done(function(data){
			obj=jQuery.parseJSON( data );
			
			window.chid=obj.id;
			window.channel = new goog.appengine.Channel(obj.token);
			goog.appengine.Socket.POLLING_TIMEOUT_MS = 1500;
			//goog.appengine.DevSocket.POLLING_TIMEOUT_MS=1000;
    window.socket = channel.open();
	//alert(window.socket);
    window.socket.onopen = onOpened;
    window.socket.onmessage = onMessage;
    window.socket.onerror = onError;
   window.socket.onclose = onClose;

			});
}

function bindTabs()
{
	$('ul.tabs').each(function(){
					// For each set of tabs, we want to keep track of
					// which tab is active and it's associated content
					var $active, $content, $links = $(this).find('a');

					// If the location.hash matches one of the links, use that as the active tab.
					// If no match is found, use the first link as the initial active tab.
					$active = $($links.filter('[href="'+location.hash+'"]')[0] || $links[0]);
					$active.addClass('active');

					$content = $($active[0].hash);

					// Hide the remaining content
					$links.not($active).each(function () {
						$(this.hash).hide();
					});

					// Bind the click event handler
					$(this).on('click', 'a', function(e){
						// Make the old tab inactive.
						$active.removeClass('active');
						$content.hide();

						// Update the variables with the new link and content
						$active = $(this);
						$content = $(this.hash);

						// Make the tab active.
						$active.addClass('active');
						$content.show();

						// Prevent the anchor's default click action
						e.preventDefault();
					});
				});
}
function bindChat()
{
	 $("#chattextform").submit(function(event){
	 
	txt=$("#chatmsg").val();
	$.ajax({
		url:'/ajax',
		data:{action:'chat', text:txt,color:currentColor, pm:currentPM },
		type :'POST'
		});
		currentPM='';
		$("div.pm").css({"border-style":"solid", "border-width":"1px","border-color":"#000"});
		
	$("#chatmsg").val('');
	 event.preventDefault();
	 
	 });
}
function bindNick()
{  $("#nickform").submit(function(event){
	 
	txt=$("#newnick").val();
	if(txt!='')
	{
	$.ajax({
		url:'/ajax',
		data:{action:'changenick', nickname:txt},
		type :'POST'
		});
	$("#newnick").val('');
	}
	 event.preventDefault();
	 
	 });
}
function bindCede()
{ 
 $("#cedeform").submit(function(event){
	 
	//txt=$("#newnick").val();
	
	$.ajax({
		url:'/ajax',
		data:{action:'cede'},
		type :'POST'
		});
	//$("#newnick").val('');
	
	 event.preventDefault();
	 
	 });
}
function fillColors()
{
	cnt=countNum(colors);
	//cnt=Math.min($("div.color").length,cnt);
	perc=Math.floor(100/cnt)-1;
	var prep=$("#colors")
	for (var key in colors)
	{
	var iDiv = document.createElement('div');
	prep.append( $(iDiv)
	    .addClass('color')
		.attr({'id':key})
		.width(perc+"%")
		.css("background-color","#"+colors[key])
		.click(function(e) {
			$("div.color").css({"border-style":"none"});
			$(this).css({"border-style":"solid", "border-width":"2px","border-color":"#000"})
            currentColor=colors[$(this).attr('id')];
        }) );
	}
}
function bindUsers()
{
	$("#sidebar").on("click","input.shardinvite", function()
	{
		var idmes=$(this).parent().siblings("input.userid");
		$.ajax({
		url:'/ajax',
		data:{action:'sendinvite',
		as: 'Shard',
		to: idmes.attr("value")
		}
		});
		$(this).hide();
		$(this).parent().parent().children("input.keeperinvite").hide();
		}
	);
	
	$("#sidebar").on("click","input.keeperinvite", function()
	{
		var idmes=$(this).parent().siblings("input.userid");
		$.ajax({
		url:'/ajax',
		data:{action:'sendinvite',
		as: 'Keeper',
		to: idmes.attr("value")
		}
		});
		$(this).hide();
		$(this).parent().parent().children("input.shardinvite").hide();
		}
	);
	$("#sidebar").on("click","input.uninvite", function()
	{
		var idmes=$(this).parent().siblings("input.userid");
		$.ajax({
		url:'/ajax',
		data:{action:'rescindinvite',
		to: idmes.attr("value")
		}
		});
		$(this).hide();
		
		}
	);
	
	$("#sidebar").on("click","input.accept", function()
	{
		var idmes=$(this).parent().siblings("input.userid");
		$.ajax({
		url:'/ajax',
		data:{action:'acceptinvite',
		from: idmes.attr("value")
		}
		});
		$(this).hide();
		
		}
	);
	
	$("#sidebar").on("click","div.pm", function()
	{
		var idmes=$(this).siblings("input.userid");
		if(idmes.attr("value")==currentPM)
		{
			$("div.pm").css({"border-style":"solid", "border-width":"1px","border-color":"#000"});
	
		currentPM='';
		}
		else
		{
		$("div.pm").css({"border-style":"solid", "border-width":"1px","border-color":"#000"});
		$(this).css({"border-style":"solid", "border-width":"2px","border-color":"#000"});
		currentPM=idmes.attr("value");
		}
		}
	);
}
function bindThreat()
{
	$("#disaster").on("click","div.threat", function()
	{
		var idmes=$(this).find(".threatid");
		
		$("#descriptionbox").html('');
		currentThreatID=idmes.attr("value");
		$.ajax({
		url:'/ajax',
		data:{action:'requestthreatdesc',
		threat: idmes.attr("value")
		}
		}).done(function(data){
			$("#descriptionbox").html(data);
		});
		$("#disaster").children(".threat").css({"border-style":"solid", "border-width":"1px","border-color":"#000"});
	$(this).css({"border-style":"solid", "border-width":"2px","border-color":"#f00"});
		
		}
	);
}
function setPingSession()
{
		$.ajax({
		url:'/ajax',
		data:{action:'pingsession'
		}
		});
	window.pinginterval=setInterval(function (){
		$.ajax({
		url:'/ajax',
		data:{action:'pingsession'
		}
		});
		},5000);
}
