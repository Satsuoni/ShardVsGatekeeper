#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import webapp2
import cgi
import logging
from google.appengine.api import users
from google.appengine.ext import ndb
#from google.appengine.ext import db
from google.appengine.ext.ndb import polymodel
from google.appengine.api import channel
from google.appengine.api import memcache
import json
import datetime
import string
import random
import re
import copy
import csv

def id_generator(size=6, chars=string.ascii_lowercase+string.ascii_uppercase + string.digits):
   return ''.join(random.choice(chars) for x in range(size))

def improperNick(user):
 if user==None: return 'Anon'
 return user.nickname()

def improperID(user):
 if user==None: return None
 if user.user_id()!=None:
   return user.user_id()
 elif user.email()!=None:
   return user.email()
 elif user.federated_identity()!=None:
   return user.federated_identity()
 else:
   return user.nickname()

DEFAULT_CHATID=u'defaultchatisoktoo'

def chat_key(chat_name=DEFAULT_CHATID):
    """Constructs a Datastore key for a chat entity with chat_name."""
    return ndb.Key('Chat', chat_name)

class GameSession(ndb.Model):
 """An individual game session """
 #id=ndb.StringProperty()
 complete=ndb.BooleanProperty()
 shardPlayer=ndb.StringProperty()
 gatekeeperPlayer=ndb.StringProperty()
 shardScore=ndb.IntegerProperty()
 gatekeeperScore=ndb.IntegerProperty()
 shardExpandedData=ndb.StringProperty(indexed=False) #not sure what goes here...
 gatekeeperExpandedData=ndb.StringProperty(indexed=False) #not sure what goes here... items?
 sessionExpandedData=ndb.StringProperty(indexed=False)
 began=ndb.DateTimeProperty()
 ended=ndb.DateTimeProperty()
 nextThreat=ndb.DateTimeProperty()
 updatedTo=ndb.DateTimeProperty()

class Threat(ndb.Model):
 """A Threat"""
 kind=ndb.StringProperty()
 stages=ndb.StringProperty(indexed=False) #increases in severity, etc a list of dictionaries
 endstage=ndb.StringProperty(indexed=False) #dictionary
 initialMin=ndb.IntegerProperty(indexed=False)
 initialMax=ndb.IntegerProperty(indexed=False) #min and max for initial severity
 onDefeat=ndb.TextProperty(indexed=False) # what happens if it is defeated, a dictionary of dictionaries
 onVictory=ndb.TextProperty(indexed=False)# what happens a keeper loses against it, a dictionary of dictionaries (by attack name)
 attackTypes=ndb.TextProperty(indexed=False)# how it can be attacked
 initiallyHidden=ndb.BooleanProperty() #will be hidden initially
 revealsOn=ndb.IntegerProperty() #will always reveal itself on this severity
 textkind=ndb.StringProperty() # threat-> string appended
 def readCSV(self,row,reader):
  try:
   self.kind=row[0]
   self.initiallyHidden=False
   while True:
    nm=row[1]
    if nm=="Stages":
      (row,res)=readListDict(row,reader,1)
      self.stages=json.dumps(res)
    elif nm=="Endstage":
      (row,res)=readListDict(row,reader,1)
      self.endstage=json.dumps(res[0])
    elif nm=="Initial Severity":
     (row,res)=readList(row,reader,1)
     self.initialMin=int(res[0])
     self.initialMax=int(res[1])
    elif nm=="Attacks":
     (row,res)=readList(row,reader,1)
     self.attackTypes=json.dumps(res)
    elif nm=="Defeated":
     (row,res)=readDictDict(row,reader,1)
     self.onDefeat=json.dumps(res)
    elif nm=="Victorious":
     (row,res)=readDictDict(row,reader,1)
     self.onVictory=json.dumps(res)
    elif nm=="Hidden":
     res=row[2]
     self.initiallyHidden=bool(int(res))
     #print self.initiallyHidden
     row=pnext(reader)
    elif nm=="Reveals On":
     res=row[2]
     self.revealsOn=int(res)
     row=pnext(reader)
    elif nm=="Text":
     cr=[]
     for a  in range(2, len(row)):
      if row[a]!='':
       cr.append(row[a])
     self.textkind=json.dumps(cr)
     row=pnext(reader)
    if row==None: break
    if row[0]!='': break
   return row
  except:
   logging.error( "Malformed csv")
   return False
#keys = Model.query().fetch(keys_only=True) 2. grab a random key key = random.sample(keys, 1)[0] 
#3. get the entity: return key.get(). of course this could be easily
class SpecialAbility(ndb.Model):
 name=ndb.StringProperty()
 dice=ndb.TextProperty()
 onVictory=ndb.TextProperty() #dictionary?
 onDefeat=ndb.TextProperty() #dictionary?
 additionalAttackTypes=ndb.TextProperty()
 onRefresh=ndb.TextProperty()

class ThreatText(ndb.Model):
   name=ndb.StringProperty()
   stage=ndb.IntegerProperty()
   minrange=ndb.IntegerProperty()
   maxrange=ndb.IntegerProperty()
   shortdesc=ndb.StringProperty()
   desc=ndb.TextProperty()

class Soldier(ndb.Model):
 sessionid=ndb.StringProperty()
 id=ndb.StringProperty()
 kind=ndb.StringProperty() #arbitrary
 power=ndb.TextProperty() #dice dictionary
 exhaustion=ndb.IntegerProperty()
 committedTo=ndb.StringProperty() #activethreat id
 victoryAbility=ndb.TextProperty() #dictionary?
 loseAbility=ndb.TextProperty() #dictionary?
 specAbs = ndb.StructuredProperty(SpecialAbility, repeated=True)#?? maybe??
 nextRefresh=ndb.DateTimeProperty()
 refreshRate=ndb.FloatProperty()
 attackTypes=ndb.TextProperty(indexed=False)# how it can  attack
 isDying=ndb.BooleanProperty()
 timeOfDeath=ndb.DateTimeProperty()

def ddictToString(ddc):
  str=''
  for key in ddc:
    if key[0]=='d':
      if str=='':
       str+=str(ddc[key])+key
      else:
       str+='+'+str(ddc[key])+key
    else:
      if str=='':
       str+=str(ddc[key])
      else:
       str+='+'+str(ddc[key])
  return str

def evalDdict(ddc):
   ret=0
   for key in ddc:
      if key[0]=='d':
       dc=int(key[1:])
       for a in range(int(ddc[key])):
         ret+=random.randint(1,dc)
      else:
       ret+=int(ddc[key])
   return ret

class GenericList(ndb.Model):
   flavor=ndb.StringProperty()
   name=ndb.StringProperty()
   value=ndb.TextProperty()

class LocationStr(ndb.Model):
 flavor=ndb.StringProperty()
 shortloc=ndb.StringProperty()
 location=ndb.TextProperty()

def valToDct(e):
    klass = e.__class__
    props = dict((k, v.__get__(e, klass)) for k, v in klass.properties().iteritems())
    return props

def pnext(it):
 try:
   rs=next(it)
 except StopIteration:
   rs=None
 return rs

def readListDict(row,reader,stp):
  lst=[]
  while True:
    cp=stp+1
    ln=len(row)
    dct={}
    while cp<ln:
     if cp+1<ln and row[cp]!='' and row[cp+1]!='':
      dct[row[cp]]=row[cp+1]
     cp=cp+2
    lst.append(dct)
    row=pnext(reader)
    if row==None: break
    filld=False
    kk=0
    while kk<=stp:
     if row[kk]!='':
       filld=True
       break
     kk+=1
    if filld: break
  return (row,lst)
       
def readDictDict(row,reader,stp):
    
    lst={}
    while True:
        if stp+1<len(row):
         kkey=row[stp+1]
        else:
         break
        cp=stp+2
        ln=len(row)
        dct={}
        while cp<ln:
            if cp+1<ln and row[cp]!='' and row[cp+1]!='':
                dct[row[cp]]=row[cp+1]
            cp=cp+2
        lst[kkey]=dct
        row=pnext(reader)
        if row==None: break
        filld=False
        kk=0
        while kk<=stp:
            if row[kk]!='':
                filld=True
                break
            kk+=1
        if filld: break
    return (row,lst)

def readList(row,reader,stp):
    lst=[]
    while True:
        cp=stp+1
        ln=len(row)
        while cp<ln:
            if row[cp]!='':
              lst.append(row[cp])
            cp=cp+1
        row=pnext(reader)
        if row==None: break
        filld=False
        kk=0
        
        while kk<=stp:
            if row[kk]!='':
                filld=True
                break
            kk+=1
        if filld:
         break
    return (row,lst)

def updateAllCsv():
    #locations
    #ndb.delete_multi(ChatMessage.query().fetch(keys_only=True))

    try:
     fl= open("csv/Locations.csv","rU")
    except:
     fl=None
    if fl:
     cr=csv.reader(fl)
     ndb.delete_multi(LocationStr.query().fetch(keys_only=True))
     for row in cr:
      en=LocationStr()
      en.flavor="metacosmere"
      en.shortloc=row[0]
      en.location=row[1]
      en.put()
    #lthreats
    try:
       fl= open("csv/Threats.csv","rU")
    except Exception as e:
      print e
      fl=None
    if fl:
      logging.warning( "Updating threats")
      cr=csv.reader(fl)
      ndb.delete_multi(Threat.query().fetch(keys_only=True))
      row=pnext(cr)
      while row!=None:
       thr=Threat()
       row=thr.readCSV(row,cr)
       if row!=False:
        thr.put()
    try:
       fl= open("csv/ThreatTexts.csv","rU")
    except Exception as e:
      print e
      fl=None
    if fl:
      cr=csv.reader(fl)
      ndb.delete_multi(ThreatText.query().fetch(keys_only=True))
      cname=''
      cstage=0
      for row in cr:
        if row[0]!='':
          cname=row[0]
        if len(row)>1 and row[1]!='':
          cstage=int(row[1])
        if len(row)>=6:
          ns=ThreatText()
          ns.name=cname
          ns.stage=cstage
          ns.minrange=int(row[2])
          ns.maxrange=int(row[3])
          ns.shortdesc=row[4]
          ns.desc=row[5]
          ns.put()
      fl.close()
    try:
       fl= open("csv/GenericLists.csv","rU")
    except:
      fl=None
    if fl:
      cr=csv.reader(fl)
      ndb.delete_multi(GenericList.query().fetch(keys_only=True))
      cname=''
      for row in cr:
        if row[0]!='':
          cname=row[0]
        for a in range(1,len(row)):
          if row[a]!='':
           gl=GenericList()
           gl.flavor="metacosmere"
           gl.name=cname
           gl.value=row[a]
           gl.put()
      fl.close()



class ActiveThreat(ndb.Model):
  #threatid=ndb.StringProperty() #id of active threat
  #sessionid=ndb.StringProperty() #id of session it belongs to
  safekind=ndb.StringProperty()
  threat=ndb.KeyProperty() #a threat type
  begins=ndb.DateTimeProperty()
  began=ndb.BooleanProperty()
  currentSeverity=ndb.IntegerProperty()
  currentStage=ndb.IntegerProperty()
  nextstageAt=ndb.DateTimeProperty()
  drawnText=ndb.TextProperty()
  drawnParameters=ndb.TextProperty() #dictionary
  is_attacked=ndb.BooleanProperty()
  noadvance=ndb.BooleanProperty()
  is_hidden=ndb.BooleanProperty()
  nukability=ndb.FloatProperty()

def activateRandomThreat(session, dsec=None, mbh=0):
  if dsec==None:
    dsec=random.expovariate(1./600.)
  dtm=datetime.datetime.now()+datetime.timedelta(seconds=dsec)
  if mbh==0:
   thr=random.choice(Threat.query().fetch())
  elif mbh==1:
   thr=random.choice(Threat.query(Threat.initiallyHidden==True).fetch())
  elif mbh==-1:
    thr=random.choice(Threat.query(Threat.initiallyHidden==False).fetch())
  nt=ActiveThreat(id=id_generator(15),parent=session.key)
  #nt.threatid=id_generator(15)
  #nt.sessionid=session.id
  nt.safekind=thr.kind
  nt.threat=thr.key
  nt.begins=dtm
  nt.nukability=0
  nt.began=False
  nt.currentSeverity=random.randint(thr.initialMin,thr.initialMax)
  nt.currentStage=0
  nt.noadvance=False
  nt.is_hidden=thr.initiallyHidden
  txtlist=json.loads(thr.textkind)
  nt.drawnText=random.choice(txtlist)
  stg=json.loads(thr.stages)
  if len(stg)==0:
   stg=json.loads(thr.endstage)
  else:
   stg=stg[0]
  if "Time" in stg:
    dt=datetime.timedelta(seconds=float(stg["Time"]))
  else:
   dt=datetime.timedelta(seconds=random.expovariate(1./300.))
  nt.nextstageAt=nt.begins+dt
  pat=re.compile("{{(.+?)}}")
  txts=ThreatText.query(ThreatText.name==nt.drawnText).fetch()
  lst=[]
  for txt in txts:
    lst+=pat.findall(txt.desc)
    lst+=pat.findall(txt.shortdesc)
  k=set(lst)
  alltxt={}
  for nm in k:
     if not nm in alltxt:
        if nm=="location" or nm=="shortloc":
         fn=random.choice(LocationStr.query(LocationStr.flavor=="metacosmere").fetch())
         alltxt["location"]=fn.location
         alltxt["shortloc"]=fn.shortloc
        else:
         try:
          fn=random.choice(GenericList.query(GenericList.flavor=="metacosmere",GenericList.name==nm).fetch())
          alltxt[nm]=fn.value
         except Exception as e:
          logging.error(str(e))
          logging.error('Name was: '+str(nm))

  nt.drawnParameters=json.dumps(alltxt)
  nt.is_attacked=False
  nt.put()
               
          
class ChatMessage(ndb.Model):
    """Models an individual chat entry with author, content, and date."""
    author = ndb.StringProperty()
    author_name = ndb.StringProperty()
    personalid =ndb.StringProperty()
    text = ndb.TextProperty(indexed=False)
    color = ndb.StringProperty(indexed=False)
    type=ndb.IntegerProperty()
    date = ndb.DateTimeProperty(auto_now_add=True)

class ChatClient(ndb.Model):
   key_name=ndb.StringProperty()#user_id
   #user_id=ndb.StringProperty()
   date = ndb.DateTimeProperty(auto_now_add=True)

class ChatUserInfo(ndb.Model):
 user_id = ndb.StringProperty()
 nickname=ndb.StringProperty()
 user_current_chat = ndb.StringProperty()
 user_type = ndb.StringProperty() #nobody, shard, gatekeeper
 is_session=ndb.BooleanProperty()
 status=ndb.StringProperty()
 userExpandedData=ndb.TextProperty(indexed=False)



def processTemplatedString(strng,dct):
  for key in dct:
    pat=re.compile("{{"+key+"}}")
    strng=re.sub(pat,dct[key],strng)
  pat=re.compile("{{%(\w+?)=(\w+?)}}(.*?){{%%}}",re.DOTALL)
  all=pat.findall(strng)
  for inst in all:
   if inst[0] in dct:
    pr=re.compile("{{%"+inst[0]+"="+inst[1]+"}}(.*?){{%%}}",re.DOTALL)
    
    if dct[inst[0]]==inst[1]:
       strng=re.sub(pr,inst[2],strng)
    else:
       strng=re.sub(pr,'',strng)
   else:
    cp=re.compile("{{%"+inst[0]+"=(\w+?)}}(.*?){{%%}}",re.DOTALL)
    strng=re.sub(cp,'',strng)
  return strng



def safeGet(thr):
    try:
        threat=thr.threat.get()
        if threat==None:
         threat=Threat.query(Threat.kind==thr.safekind).fetch(1)[0]
    except:
        if thr.safekind==None:
         thr.safekind='None'
        logging.error("Threat exceptioned : "+thr.safekind)
        threat=Threat.query(Threat.kind==thr.safekind).fetch(1)[0]
    return threat


def threatToBlock(thr):
  thrx=memcache.get("threat")
  if thrx!=None:
   tx=thrx
  else:
   fl=open("threat.html")
   tx=fl.read()
   fl.close()
   memcache.add("threat",tx,120)
  ttxs=ThreatText.query(ThreatText.name==thr.drawnText,
                        ThreatText.stage<=thr.currentStage).order(-ThreatText.stage).fetch()
  ttx=None
  for tcx in ttxs:
    if tcx.minrange<=thr.currentSeverity and tcx.maxrange>=thr.currentSeverity:
      ttx=tcx
      break
  dct1=json.loads(thr.drawnParameters)
  short=processTemplatedString(ttx.shortdesc,dct1)
  #long=processTemplatedString(ttx.desc,dct1)
  dct={}
  threat=safeGet(thr)

  dct["threatid"]=str(thr.key.id())
  dct["threattype"]=threat.kind.upper()
  dct["threatlocation"]=dct1["shortloc"]
  dct["threatseverity"]=str(thr.currentSeverity)
  if not thr.began:
   dct["threatstatus"]="IMPENDING"
  elif thr.noadvance:
   dct["threatstatus"]="STALLED"
  elif thr.is_hidden:
   dct["threatstatus"]="HIDDEN"
  else:
   dct["threatstatus"]="ACTIVE"
  if dct["threatstatus"]=="IMPENDING":
   dt=thr.begins-datetime.datetime.now()
  else:
   dt=thr.nextstageAt-datetime.datetime.now()
  dsc=dt.total_seconds()
  if dsc<0:
   dsc=0
  minutes, seconds=divmod(dsc,60)
  dct["threattimer"]="%d : %02d" %(int(minutes), int(seconds))
  dct["threatshortdesc"]=short
  ret=processTemplatedString(tx,dct)
  return ret

def threatToDesc(thr):
  #fl=open("threat.html")
  #tx=fl.read()
  #fl.close()
  ttxs=ThreatText.query(ThreatText.name==thr.drawnText,
                        ThreatText.stage<=thr.currentStage).order(-ThreatText.stage).fetch()
  ttx=None
  for tcx in ttxs:
    if tcx.minrange<=thr.currentSeverity and tcx.maxrange>=thr.currentSeverity:
      ttx=tcx
      break
  dct1=json.loads(thr.drawnParameters)
  short=processTemplatedString(ttx.shortdesc,dct1)
  long=processTemplatedString(ttx.desc,dct1)
  return long

def getThreadBlocks(user,session):
   if session.shardPlayer==user.user_id: #Shardic vision
     thrs=ActiveThreat.query(ancestor=session.key).fetch()
   else:
     thrs=ActiveThreat.query(ActiveThreat.is_hidden==False,ActiveThreat.began==True,ancestor=session.key).fetch()
   cn=''
   for thr in thrs:
    cn+=threatToBlock(thr)
   return cn



def Chat(author,name,color,text,personalid='',type=0,chatid=DEFAULT_CHATID):
  key=chat_key(chatid)
  msg=ChatMessage(parent=key)
  msg.author_name=name
  msg.author=author
  msg.color=color
  msg.text=text
  msg.type=type
  msg.personalid=personalid
  msg.put()

class MainHandler(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
         usrdat=requestOrCreateUser(user)
         if usrdat.is_session:
          self.redirect("/session")
         else:
          f=open("core.html")
          k=f.read()
          f.close()
          self.response.write(str(k))
         #user_id() nickname()
        else:
         self.redirect(users.create_login_url(self.request.uri))

class RefreshHandler(webapp2.RequestHandler):
    def get(self):
        updateAllCsv()
        self.response.write(str("Refreshed csv files"))

class SessionHandler(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            usrdat=requestOrCreateUser(user)
            if not usrdat.is_session:
             self.redirect("/")
            else:
             usrdat=requestOrCreateUser(user)
             f=open("session.html")
             k=f.read()
             f.close()
             self.response.write(str(k))
        #user_id() nickname()
        else:
            self.redirect(users.create_login_url(self.request.uri))

USER_DATA='alluserdatagoeshere'
SESSION_DATA='allsessiondatacomehere'

def requestUserid(id):
   userDataq=ChatUserInfo.query(ChatUserInfo.user_id==id,ancestor=ndbkey(USER_DATA)).fetch(1)
   if len(userDataq)>0:
    return userDataq[0]
   else:
    return None


def ndbkey(str):
 return ndb.Key('Key', str)

def parsediceint(str):
   res=0
   
   return res

def requestOrCreateUser(user):
    id=improperID(user)
    userDataq=ChatUserInfo.query(ChatUserInfo.user_id==id, ancestor=ndbkey(USER_DATA)).fetch(1)
    if len(userDataq)>0:
            userData=userDataq[0]
    else:
        userData=ChatUserInfo(parent=ndbkey(USER_DATA))
        userData.user_id=id
        userData.nickname=id_generator(7)#improperNick(user)
        userData.user_current_chat=DEFAULT_CHATID
        userData.is_session=False
        userData.status="normal"
        dct={}
        js=json.dumps(dct)
        userData.userExpandedData=js
        userData.user_type="nobody"
        userData.put()
    return userData

def gotoSession(userdata):
    msg={}
    msg["kind"]="gotoSession"
    jmsg=json.dumps(msg)
    channel.send_message(userdata.user_id,jmsg)

def gotoChat(userdata):
    msg={}
    msg["kind"]="gotoChat"
    jmsg=json.dumps(msg)
    channel.send_message(userdata.user_id,jmsg)

def updateUsers():
   msg={}
   msg["kind"]="updateusers"
   jmsg=json.dumps(msg)
   for gc in ChatClient.query().fetch():
     #usr=requestUserid(gc.key_name)
     #if usr and usr.user_current_chat==userData.user_current_chat:
     channel.send_message(gc.key_name,jmsg)


def newShardData():
  data={}
  data["ShardName"]="Hoidium"
  return json.dumps(data)

def newKeeperData():
  data={}
  return json.dumps(data)

def newSessionData():
    data={}
    data["shardCur"]=0
    data["shardMax"]=random.randint(1,6)+random.randint(1,6)+random.randint(1,6)+2
    data["items"]=[]
    data["disasters"]=[]
    return json.dumps(data)

def updateStateString(session, userid):
    sd=json.loads(session.sessionExpandedData)
    msg={}
    msg["kind"]="updatestate"
    dt=session.ended- datetime.datetime.now()
    dt=dt.total_seconds()
    hrs, rem=divmod(dt,3600)
    mnt, sc=divmod(rem, 60)
    if hrs<0 or mnt<0:
      hrs=0
      mnt=0
    msg["stimer"]="Time left: %02d:%02d"% (hrs,mnt)
    msg["shardpower"]="Shardic power: %d/%d"%(int(sd["shardCur"]),int(sd["shardMax"]))
    msg["gscore"]="Gatekeeper: %d"%(int(session.gatekeeperScore))
    msg["sscore"]="Shard: %d"%(int(session.shardScore))
    if userid==session.shardPlayer: #shard or both
     msg["ptype"]="Shard"
     msg["pkind"]="TODO"
    else:#gatekeeper
     msg["ptype"]="Gatekeeper"
     msg["pkind"]="TODO"
    return json.dumps(msg)


def writeupSession(session):
  announceGeneral("Session is complete",session.key_name)
  pass



def getThreatStage(threat,cs):
    stages=json.loads(threat.stages)
    if cs<len(stages):
        stage=stages[cs]
        if not "Nukability" in stage:
          stage["Nukability"]=0
    else:
        stage=json.loads(threat.endstage)
        if not "Nukability" in stage:
            stage["Nukability"]=0.2

    return stage

def announceThreat(thr, ses, txt):
   if thr.is_hidden:
     announcePersonal(txt,ses.shardPlayer,ses.key.id())
   else:
    announceGeneral(txt,ses.key.id())



def updateSession(session): #timewise
    sema=memcache.get(session.key.id())
    if sema!=None and sema=='semaphore':
      return
    memcache.add(session.key.id(),'semaphore',20)
    #logging.warning("session")
    cdt=datetime.datetime.now()
    if session.updatedTo==None:
       session.updatedTo=session.began
    
    if session.complete and session.updatedTo>=session.ended:
      return
    if cdt>=session.ended and session.updatedTo>=session.ended:
        session.complete=True
        session.put()
        return
    if cdt>=session.ended and session.updatedTo<session.ended:
     cdt=session.ended
    spawned=False
    nd=json.loads(session.sessionExpandedData)
    #update threats
    while cdt>session.nextThreat:
      session.nextThreat+=datetime.timedelta(seconds=random.expovariate(1./500.))
      activateRandomThreat(session,random.expovariate(1./500.))
    thrs=ActiveThreat.query(ancestor=session.key).fetch()
    for thr in thrs:
      delthr=False
      threat=safeGet(thr)
      if not thr.began and cdt>thr.begins:
         thr.began=True
         thr.put()
         announceThreat(thr,session,"A new threat emerges")
         announceThreat(thr,session,threatToDesc(thr))
    

      while thr.nextstageAt<=cdt:
          
        #logging.warning("updating")
         # if not spawned:
         #  spawned=True
         #  activateRandomThreat(session,random.expovariate(1./500.))
        cs=thr.currentStage
        stage=getThreatStage(threat,cs)
        if thr.noadvance:
          thr.noadvance=False
          if "Dissolve" in stage:
            if random.random()<float(stage["Dissolve"]):#threat is done
               delthr=True
               announceThreat(thr,session,"A %s dissipates peacefully" %(threat.kind))
          if "Time" in stage and not delthr:
              ndt=datetime.timedelta(seconds=float(stage["Time"]))
              thr.nextstageAt=cdt+ndt
        else:
         if "Damage" in stage:
          dmg=stage["Damage"]
          if dmg=="Severity":
            dmg=thr.currentSeverity
          else:
            dmg=int(dmg)
          if dmg!=0:
           announceThreat(thr,session,"%s deals %d damage!"%(threat.kind, dmg))
          session.gatekeeperScore-=dmg
          if dmg>0 and thr.is_hidden:
            thr.is_hidden=False
            announceThreat(thr,session,"A new threat, %s is revealed to Gatekeeper!"%(threat.kind))
            announceThreat(thr,session,threatToDesc(thr))
         if "Increase" in stage:
          if stage["Increase"]=="Severity":
           ii=thr.currentSeverity
          else:
           ii=int(stage["Increase"])
          thr.currentSeverity+=ii
          if ii>0:
           announceThreat(thr,session,"%s becomes more threatening" %(threat.kind))
          if ii<0:
           announceThreat(thr,session,"%s becomes less threatening..." %(threat.kind))
          if thr.is_hidden and thr.currentSeverity>=threat.revealsOn:
             thr.is_hidden=False
             announceThreat(thr,session,"A new threat, %s is revealed to Gatekeeper!"%(threat.kind))
         if thr.nukability==None:
           thr.nukability=0
         thr.nukability+=stage["Nukability"]
         if thr.nukability>=1.0:
            tx=processTemplatedString("Military grows frustrated with your inability to deal with %s in {{location}}, and nukes it to kingdom come!" % (threat.kind),json.loads(thr.drawnParameters))
            thr.gatekeeperScore-=15
            announceThreat(thr,session,tx)
            delthr=True
         if "Dissolve" in stage and not delthr:
            if random.random()<float(stage["Dissolve"]):#threat is done
               delthr=True
               announceThreat(thr,session,"A %s dissipates peacefully" %(threat.kind))
    ##advance
         oldtext=threatToDesc(thr)
         thr.currentStage+=1
         newtext=threatToDesc(thr)
         if oldtext!=newtext:
            announceThreat(thr,session,newtext)
         stage=getThreatStage(threat,cs+1)
         if "Time" in stage and not delthr:
            ndt=datetime.timedelta(seconds=float(stage["Time"]))
            thr.nextstageAt+=ndt
         else:
            thr.nextstageAt+=datetime.timedelta(seconds=random.expovariate(1./500.))
                
        if delthr:
         thr.key.delete()
         break
      if delthr:
       continue
      if not delthr:
       thr.put()

     ##soldier update
    if cdt>=session.ended:
     session.complete=True
     session.put()
     writeupSession(session)
    session.updatedTo=cdt
    session.put()
    #logging.warning("endupdate")
    memcache.set(session.key.id(),'nothing',1)



def completeInvite(userData,inviter,inv):
  #clean up invites
  ed1=json.loads(userData.userExpandedData)
  if "invites" in ed1:
   del ed1["invites"]
   stm=json.dumps(ed1)
   userData.userExpandedData=stm
  ed2=json.loads(inviter.userExpandedData)
  if "invites" in ed2:
    del ed2["invites"]
    stm=json.dumps(ed2)
    userData.userExpandedData=stm
  sid=id_generator(13)
  userData.user_current_chat=sid
  inviter.user_current_chat=sid
  userData.is_session=True
  inviter.is_session=True
  ses=GameSession(parent=ndbkey(SESSION_DATA),id=sid)
  if inv=="Shard":
    ses.shardPlayer=inviter.user_id
    ses.gatekeeperPlayer=userData.user_id
  else:
    ses.shardPlayer=userData.user_id
    ses.gatekeeperPlayer=inviter.user_id
  ses.shardScore=0
  ses.complete=False
  ses.gatekeeperScore=0
  ses.shardExpandedData=newShardData()
  ses.gatekeeperExpandedData=newKeeperData()
  ses.began=datetime.datetime.now()
  ses.ended=ses.began+datetime.timedelta(hours=2)
  ses.sessionExpandedData=newSessionData()
  ses.updatedTo=ses.began
  ses.nextThreat=datetime.datetime.now()#+datetime.timedelta(seconds=random.expovariate(1./500.))
  ses.put()
  userData.put()
  inviter.put()
  activateRandomThreat(ses, 0)
  gotoSession(userData)
  gotoSession(inviter)


def cedeSession(userData):
  sid=userData.user_current_chat
  ses=GameSession.get_by_id(sid,parent=ndbkey(SESSION_DATA))
  if ses.shardPlayer==userData.user_id:
     sn="Shard"
  else:
     sn="Gatekeeper"
  dat=datetime.datetime.now()
  if dat>=ses.ended or ses.complete==True: ##session is complete, just withdraw
    userData.is_session=False
    if dat<ses.ended:
      ses.ended=dat
    userData.user_current_chat=DEFAULT_CHATID
    userData.put()
    announceGeneral("%s %s has withdrawn from session" % (sn, userData.nickname), sid)
    ses.complete=True
    ses.put()
  else:# actually cede from session
   ses.complete=True
   if dat<ses.ended:
           ses.ended=dat
   userData.is_session=False
   userData.user_current_chat=DEFAULT_CHATID
   userData.put()
   if sn=="Shard":
    ses.shardScore=0
    if ses.gatekeeperScore<=ses.shardScore:
      ses.gatekeeperScore=ses.shardScore+10
    announceGeneral("%s %s has ceded victory to Gatekeeper by splintering itself and destroying its own mind!" % (sn, userData.nickname), sid)
   else:
    ses.gatekeeperScore=0
    if ses.shardScore<=ses.gatekeeperScore:
      ses.shardScore=ses.gatekeeperScore+15
    announceGeneral("%s %s has released Shard and committed suicide at the same time!" % (sn, userData.nickname), sid)
   ses.put()
  gotoChat(userData)

def connectChannel(clid):
    user = users.get_current_user()
    ac = ChatClient.query(ChatClient.key_name==clid).fetch(1)
    if ac==None or len(ac)==0:
        ac=ChatClient(key_name = clid)
        ac.user_id=improperID(user)
        ac.put()
    updateUsers()
def disconnectChannel(clid):
        msg={}
        msg["kind"]="ping"
        channel.send_message(clid,json.dumps(msg))
        ac = ChatClient.query(ChatClient.key_name==clid).fetch()
        if len(ac)>0:
           for bc in ac:
            bc.key.delete()
        updateUsers()


def sendall(jmsg,cchat):
    sent=[]
    for gc in ChatClient.query().fetch():
            usr=requestUserid(gc.key_name)
            #if usr.user_id in sent:
            #    gc.key.delete()
            if usr and usr.user_current_chat==cchat and not usr.user_id in sent:
                sent.append(usr.user_id)
                channel.send_message(gc.key_name,jmsg)

def announceGeneral(text,chid=DEFAULT_CHATID ):
    idd="system"
    Chat(idd,'',"993399",text,'',1,chid )
    msg={}
    msg["id"]=id_generator(10)
    dtn=datetime.datetime.now()
    msg["date"]=dtn.strftime("%a, %y-%m-%d")
    msg["time"]=dtn.strftime("[%H:%M:%S]")
    msg["name"]=''
    msg["text"]=cgi.escape(text)
    msg["kind"]="updatechat"
    msg["color"]="993399"
    msg["type"]=1
    jmsg=json.dumps(msg)
    sendall(jmsg,chid)

def announcePersonal(text,pid,chid=DEFAULT_CHATID):
    idd="system"
    Chat(idd,'system',"770099",text,pid,1,chid)
    msg={}
    msg["id"]=id_generator(10)
    dtn=datetime.datetime.now()
    msg["date"]=dtn.strftime("%a, %y-%m-%d")
    msg["time"]=dtn.strftime("[%H:%M:%S]")
    msg["name"]=''
    msg["text"]=cgi.escape(text)
    msg["kind"]="updatechat"
    msg["color"]="770099"
    msg["type"]=1
    jmsg=json.dumps(msg)
    sendall(jmsg,DEFAULT_CHATID)

class AjaxHandler(webapp2.RequestHandler):
    def get(self):
     self.post()
    
    def post(self):
      action=self.request.get('action','nothing')
      user = users.get_current_user()
      
      if action=='nothing':
       self.response.write('')
       return
      elif action=='chat':
       id=improperID(user)
       connectChannel(id)
       userData=requestUserid(id)
       #if user:
       # name=user.nickname()
       #else:
       # name="Anonymouse"
       name=userData.nickname
       text=self.request.get('text','')
       personalid=self.request.get('pm','')
       color=self.request.get('color','000000')
       Chat(id,name,color,text,personalid,0,userData.user_current_chat )
       msg={}
       msg["id"]=id
       dtn=datetime.datetime.now()
       msg["date"]=dtn.strftime("%a, %y-%m-%d")
       msg["time"]=dtn.strftime("[%H:%M:%S]")
       msg["name"]=name
       msg["text"]=cgi.escape(text)
       msg["kind"]="updatechat"
       msg["color"]=color
       msg["type"]=0
       jmsg=json.dumps(msg)
       if personalid!='':
         gc =ChatClient.query(ChatClient.key_name==personalid).fetch(1)
         if len(gc)>0:
          channel.send_message(personalid,jmsg)
       else:
        sendall(jmsg,userData.user_current_chat)
       #logging.error("chatted")
       self.response.write('')
       return
      elif action=='refreshchat':
       id=improperID(user)
       userData=requestUserid(id)
       maxnum=self.request.get('number','30')
       try:
         maxnum=int(maxnum)
       except:
         maxnum=30
       chatid=userData.user_current_chat
       if chatid=='':
          chatid=DEFAULT_CHATID
       id=improperID(user)
       query = ChatMessage.query(ChatMessage.personalid.IN(["",id]), ancestor=chat_key(chatid)).order(-ChatMessage.date)
       #query.filter()
       messages = query.fetch(maxnum)
       msgs=[]
       for msg in messages:
         dct=msg.to_dict()
         dct["text"]=cgi.escape(dct["text"])
         dt=dct["date"]
         dct["name"]=dct["author_name"]
         dct["date"]=dt.strftime("%a, %y-%m-%d")
         dct["time"]=dt.strftime("[%H:%M:%S]")
         msgs.append(dct)
       js=json.dumps(msgs)
       self.response.write(str(js))
       updateUsers()
       return
      elif action=='pingsession':
       id=improperID(user)
       userData=requestUserid(id)
       if userData and userData.is_session:
         #print userData.user_current_chat
         ses=GameSession.get_by_id(userData.user_current_chat,parent=ndbkey(SESSION_DATA))# query(GameSession.id==userData.user_current_chat).fetch()
         if ses!=None:
          
          updateSession(ses)
          channel.send_message(ses.shardPlayer,updateStateString(ses,ses.shardPlayer))
          channel.send_message(ses.gatekeeperPlayer ,updateStateString(ses,ses.gatekeeperPlayer))
          msg={}
          msg["kind"]="updatethreat"
          msg["blocks"]=getThreadBlocks(userData,ses)
          jmsg=json.dumps(msg)
          channel.send_message(userData.user_id,jmsg)
       self.response.write('')
      elif action=='negotiate':
        userData=requestOrCreateUser(user)
        id=improperID(user)
        if id==None:
          id=id_generator(17)
        token = channel.create_channel(id)
        dct={}
        dct["token"]=token
        dct["id"]=id
        js=json.dumps(dct)
        self.response.write(str(js))
        return
      elif action=='opened':
         id=improperID(user)
         udat=requestUserid(id)
         ac = ChatClient.query(ChatClient.key_name==id).fetch(1)
        # print "connecting"
         if ac==None or len(ac)==0:
            ac=ChatClient(key_name = id)
            ac.user_id=improperID(user)
            ac.put()
         updateUsers()
         if udat and (udat.user_current_chat==DEFAULT_CHATID):
          announceGeneral(udat.nickname+ " has joined.")
      elif action=='acceptinvite':
        userData=requestOrCreateUser(user)
        id=improperID(user)
        fromid=self.request.get('from','')
        if fromid!='':
          inviter=requestUserid(fromid)
          if inviter:#got the id right
            edat=json.loads(inviter.userExpandedData)
            if "invites" in edat:#he did, in fact, invite you?
              if id in edat["invites"]:
                 #seal the invitation
                 completeInvite(userData,inviter,edat["invites"][id])
                 self.response.write('')
                 return
        self.response.write('error')
      elif action=='rescindinvite':
          userData=requestOrCreateUser(user)
          id=improperID(user)
          fromid=self.request.get('to','')
          inviter=requestUserid(fromid)
          if inviter:#got the id right
              edat=json.loads(userData.userExpandedData)
              if "invites" in edat:
                 invites=edat["invites"]
              else:
                  invites={}
              if fromid in invites:
                announcePersonal("The invitation from %s has been rescinded" %(inviter.nickname),fromid)
                del invites[fromid]
              edat["invites"]=invites
              userData.userExpandedData=json.dumps(edat)
              userData.put()
              updateUsers()
      elif action=='sendinvite':
          id=improperID(user)
          userData=requestUserid(id)
          astype=self.request.get('as',None)
          usrid=self.request.get('to',None)
          if astype and usrid:
           ud=requestUserid(usrid)
           if ud:
            edat=json.loads(userData.userExpandedData)
            if "invites" in edat:
             invites=edat["invites"]
            else:
                invites={}
            if astype!='Shard': astype='Keeper'
            invites[usrid]=astype
            edat["invites"]=invites
            userData.userExpandedData=json.dumps(edat)
            userData.put()
            announcePersonal("%s has sent you an invitation" %(userData.nickname),usrid)
            updateUsers()
      
          self.response.write('')
      elif action=='changenick':
            id=improperID(user)
            nick=self.request.get('nickname',id_generator(7))
            userData=requestUserid(id)
            if userData:
              userData.nickname=nick
              userData.put()
              updateUsers()
            self.response.write('')
      elif action=='cede':
       id=improperID(user)
       userData=requestUserid(id)
       if userData.is_session:
         cedeSession(userData)
       self.response.write('')
      elif action=='requestthreatdesc':
        threat=self.request.get('threat',None)
        userData=requestUserid(improperID(user))
        session=GameSession.get_by_id(userData.user_current_chat,parent=ndbkey(SESSION_DATA))
        if session==None:
          logging.warning("Invalid threat request")
          return
        if threat:
          thr=ActiveThreat.get_by_id(threat,parent=session.key)
          if thr!=None:
            dat=threatToDesc(thr)
            
            if session.shardPlayer==userData.user_id:
             nk=thr.nukability
             if nk==None:
               nk=0
               thr.nukability=0
               thr.put()
             dat+="<br> <span style=\"color:#ff0000;\">Nukability: %1.2f</span>" %(nk)
             logging.warning(dat)
            self.response.write(str(dat))
            return
        self.response.write('')
      elif action=='getuserlist':
          id=improperID(user)
          userData=requestUserid(id)
          output=''
          f=open("user.html")
          k=f.read()
          f.close()
          edat=json.loads(userData.userExpandedData)
          if "invites" in edat:
            invites=edat["invites"]
          else:
            invites=[]
          #rid=[k[0] for k in invites]
          listed=[]
          for usron in ChatClient.query().fetch():
            uid=usron.key_name
            usr=requestUserid(uid)
            if usr.user_current_chat==userData.user_current_chat and not uid in listed:
              listed.append(uid)
              dct={}
              st=copy.copy(k)
              dct["userid"]=usr.user_id
              dct["usernick"]=usr.nickname
              dct["mode"]="normal"
              if usr.user_id in invites:
               dct["mode"]="invited"
              ed=json.loads(usr.userExpandedData)
              if "invites" in ed:
                 #edid=[k[0] for k in ed["invites"]]
                 if userData.user_id in ed["invites"]:
                    if dct["mode"]!="invited":
                     dct["mode"]="invitee"
                    else:
                     dct["mode"]="both"

                    dct["astype"]=ed["invites"][userData.user_id]
              if userData.is_session:
                dct["mode"]="session"
              st=processTemplatedString(st,dct)
              output+=st
          self.response.write(str(output))
      elif action=='putmeback':
       id=improperID(user)
       logging.warning("Putmeback triggered")
       connectChannel(id)
       self.response.write('')
      ## Other actions: send invite
      else:
       self.response.write('')
       return


class ConnectHandler(webapp2.RequestHandler):
 def post(self):
     client_id = self.request.get('from')
     connectChannel(client_id)

class DisconnectHandler(webapp2.RequestHandler):
    def post(self):
        client_id = self.request.get('from')
        disconnectChannel(client_id)



app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/ajax', AjaxHandler),
    ('/session', SessionHandler),
    ('/refresh', RefreshHandler),
    ('/_ah/channel/connected/',ConnectHandler),
    ('/_ah/channel/disconnected/',DisconnectHandler)
], debug=True)
