###############################################################################
# This Addon:
# Inspired by "XBMCState Vera Plugin XBMC Addon"
# Thanks to chixxi for the vera plugin and jordan Hackworth for the script idea
# http://www.jordanhackworth.com/home-automation-with-xbmc/
# http://windowsmediacenter.blogspot.co.uk/2013/02/xbmc-vera-home-automationbasic.html
# http://apps.mios.com/plugin.php?id=3346
###############################################################################

###############################################################################
# XBMC Reference
#
# http://mirrors.xbmc.org/docs/python-docs/frodo/
# https://github.com/xbmc/xbmc/blob/master/xbmc/interfaces/json-rpc/PlayerOperations.cpp 
# https://github.com/xbmc/xbmc/blob/master/xbmc/cores/IPlayerCallback.h                    
# https://github.com/xbmc/xbmc/blob/master/xbmc/guilib/WindowIDs.h
# https://github.com/jaredquinn/xbmcshell/blob/master/xbmcshell
###############################################################################

import sys
import xbmc
import xbmcgui                                                                                                                                                                      
import xbmcaddon
import time
import socket
import json #simplejson
import re

settings          = xbmcaddon.Addon(id='service.indigo')
indigo_ip         = settings.getSetting( "indigo_ip" )
indigo_port       = settings.getSetting( "indigo_port" )

debouncing_video  = float(settings.getSetting( "debounce_video"))
debouncing_audio  = float(settings.getSetting( "debounce_audio"))

__addonname__     = settings.getAddonInfo('name')
__icon__          = settings.getAddonInfo('icon')

plugin_start      = "Plugin started"
plugin_error      = "Please insert Indigo information in the addon setting"
time1             = 5000
time2             = 3000

sock        = None
debugMode   = False
settingsOK  = False
lastMedia   = ""
lastMenu    = ""
lastTitle   = ""
lastVolume  = 0
lastMuted   = False
currMedia   = ""
currTitle   = ""
currVolume  = 0
currMuted   = False
lastWindow  = 0

def get_installedversion():
    # retrieve current installed version
    #version=xbmc.Application.GetProperties(properties=['version'])['version']['major']
    #http://www.tayunsmart.com/otaupdate/xbmc/s9/addons/plugin.program.super.favourites/utils.py
    xQuery = xbmc.executeJSONRPC('{ "jsonrpc": "2.0", "method": "Application.GetProperties", "params": {"properties": ["version", "name"]}, "id": 1 }')
    xQuery = unicode(xQuery, 'utf-8', errors='ignore')
    xQuery = jsoninterface.loads(xQuery)
    version_installed = []
    if xQuery.has_key('result') and xQuery['result'].has_key('version'):
        version_installed  = xQuery['result']['version']
    return version_installed

def debugLog (message):
    global debugMode
    if debugMode == True:
        print('Indigo.Addon: Debug: ' + message)   

def errorLog (message):
    print('Indigo.Addon: ERROR: ' + message)   

def indigoSendMsg(message):
    global sock
    try:
        sock.sendto (message, (indigo_ip , int(indigo_port)))
        debugLog ('Sent message to Indigo plugin:' + message)   
    except socket.error:
        errorLog ('indigoSendMsg. Socket error: ' + str(sys.exc_info()[1][0]) + ',' + str(sys.exc_info()[1][1] ))

def notifyEventApp(event):
    debugLog ('notifyEventApp(' + event + ')') 
    event = event.lower()
    message = '<type>app</type>'
    message = message + '<event>' + event + '</event>'
    indigoSendMsg(message)

def notifyEventPlayer(event, media):
    global currTitle
    global currVolume
    debugLog ('notifyEventPlayer(' + event + ',' + media + ')')
    event = event.lower()    
    message = '<type>player</type>'
    message = message + '<event>' + event + '</event>'
    message = message + '<media>' + media + '</media>'
    message = message + '<title>' + currTitle + '</title>'
    indigoSendMsg(message)

def notifyEventMenu(event):   
    debugLog ('notifyEventMenu(' + event + ')')
    event = event.lower()
    message = '<type>menu</type>'
    message = message + '<menu>' + event + '</menu>'
    indigoSendMsg(message)
    
def notifyEventVolume(volume,muted):   
    debugLog ('notifyEventVolume(' + str(volume) + ')')
    message = '<type>volume</type>'
    message = message + '<volume>' + str(volume) + '</volume>'
    message = message + '<muted>' + str(muted).lower() + '</muted>'
    indigoSendMsg(message)

def notifyEventTitle(title):   
    debugLog ('notifyEventTitle(' + title + ')')
    title = title.strip()
    if title == '':
        title = '.'
    message = '<type>title</type>'
    message = message + '<title>' + title + '</title>'
    indigoSendMsg(message)

def checkEventMenu(event):
    global lastMenu
    if event != lastMenu:
        debugLog ('Old menu = ' + lastMenu + '. New menu = ' + event)   
        notifyEventMenu (event)
        lastMenu = event

def checkEventVolume():
    global lastVolume
    global lastMuted

    xVolume = 0
    xMute   = False

    xVolume, xMuted = getCurrentVolume()
    if (xVolume != lastVolume) or (xMuted != lastMuted):
        notifyEventVolume(xVolume,xMuted)

    lastVolume = xVolume
    lastMuted  = xMuted

def checkEventTitle():
    global currTitle

    if xbmc.Player().isPlaying(): 
        xTitle = getCurrentMediaTitle()
        if (xTitle != currTitle) :
            notifyEventTitle(xTitle)
        currTitle = xTitle

def getCurrentMediaType():
    # none,video, audio, picture, livetv, tvshow, radio
    global lastMenu
    global lastWindow

    lMedia  = 'none'
    lWindow = xbmcgui.getCurrentWindowId()

    if xbmc.Player().isPlaying():          
        if xbmc.Player().isPlayingVideo():
            if xbmc.getCondVisibility('VideoPlayer.Content(episodes)'): 
                if xbmc.getInfoLabel('VideoPlayer.Season') != "" and xbmc.getInfoLabel('VideoPlayer.TVShowTitle') != "":
                    lMedia = 'tvshow' 
            if xbmc.getCondVisibility('VideoPlayer.Content(livetv)'):  
                lMedia = 'livetv'     
            if lMedia == 'none':                                                                                                                                    
                lMedia = 'video'
                if lWindow == 10614:
                    lMedia = 'livetv'
                #if xbmc.Pvr().IsPlayingTv(): 
                #    lMedia = 'livetv'   
        if xbmc.Player().isPlayingAudio():
            if xbmc.getCondVisibility('VideoPlayer.Content(livetv)'): 
                lMedia = 'radio'
            else:
                lMedia = 'audio' 
        if lWindow == 10614:
            lMedia = 'livetv' 
        if lWindow >= 10694 and lWindow <= 10699:
            lMedia = 'livetv' 
        if lastMenu == 'livetv':
            lMedia = 'livetv' 
      
    return lMedia

def getCurrentVolume():
    xQuery  = ''
    xResult = ''
    xVolume = 0
    xMuted  = False

    try:
        xQuery  = '{"jsonrpc": "2.0", "method": "Application.GetProperties", "params": { "properties": [ "volume", "muted" ] }, "id": 1}'
        xResult = xbmc.executeJSONRPC( xQuery )
        xMatch  = re.search( '"volume": ?([0-9]{1,3})', xResult )
        xVolume = int(xMatch.group(1)) 
        if bool (re.search ('"muted": true',xResult)):
            xMuted = True
    except:
        xVolume = lastVolume
        xMuted  = lastMuted
        pass

    return xVolume, xMuted


def getCurrentMediaTitle():
    lTitle = '' 
    try:
        lMedia = getCurrentMediaType()
        if lMedia == 'tvshow':
            lTitle = xbmc.getInfoLabel('VideoPlayer.TVShowTitle')
            if lTitle > '':
                lTitle = lTitle + ': ' + xbmc.getInfoLabel('VideoPlayer.Title') 
        if lMedia == 'livetv':
            lTitle = xbmc.getInfoLabel('VideoPlayer.ChannelName') 
            if lTitle > '':
                lTitle = lTitle + ': ' + xbmc.getInfoLabel('VideoPlayer.Title') 
        if lMedia == 'radio':
            lTitle = xbmc.getInfoLabel('MusicPlayer.ChannelName')
        if lTitle == '':    
            if xbmc.Player().isPlaying(): 
                if xbmc.Player().isPlayingVideo():
                    lTitle = xbmc.getInfoLabel('VideoPlayer.Title') 
                if xbmc.Player().isPlayingAudio():
                    lTitle = xbmc.getInfoLabel('MusicPlayer.Title')
    except:
        lTitle = ''
    lTitle = lTitle.replace('<', '')
    lTitle = lTitle.replace('>', '')
    lTitle = lTitle.replace('&', '')
    return lTitle

def watchNavigation():
    global lastMedia
    global lastMenu
    global lastWindow
    global lastVolume
    global lastMuted

    checkEventVolume()
    checkEventTitle()

    currWindow = (xbmcgui.getCurrentWindowId())
                                                                                                 
    # menu Home
    if currWindow == 10000:
        checkEventMenu ('home')
    if currWindow == 10001:
        checkEventMenu ('program')
    if currWindow == 10002:
        checkEventMenu ('picture')

    # menu Sistema    
    if currWindow == 10004:
        checkEventMenu ('settings')
    if currWindow == 10007:
        checkEventMenu ('settings')
    if (currWindow >= 10012) and (currWindow <= 10019):
        checkEventMenu ('settings')
    if currWindow == 10021:
        checkEventMenu ('settings')        

    # menu PVR
    if (currWindow >= 10601) and (currWindow <= 10613):
        checkEventMenu ('livetv')
   
    # menu Video
    if currWindow == 10006:
        checkEventMenu ('video')
    if currWindow == 10024:
        checkEventMenu ('video')
    if currWindow == 10025:
        checkEventMenu ('video')
    if currWindow == 10028:
        checkEventMenu ('video')

    # Menu audio        
    if currWindow == 10005:
        checkEventMenu ('music')
    if currWindow == 10500:
        checkEventMenu ('music')
    if currWindow == 10501:
        checkEventMenu ('music')
    if currWindow == 10502:
        checkEventMenu ('music')

    # Menu Meteo
    if currWindow == 12600:
        checkEventMenu ('weather')

    lastWindow = currWindow

#class MyApplication(xbmc.Application):                                                                                                                                                             
                                                                                                                                                                                     
#        def __init__ (self):                                                                                                                                                             
#                xbmc.Application.__init__(self)   

#        def OnVolumeChanged 

class MyPlayer(xbmc.Player):                                                                                                                                     
        def __init__ (self):                                                                                                                                                             
            xbmc.Player.__init__(self)              
            debugLog ('Player init')    
                     
        def onPlayBackStarted(self):
            global currMedia
            global currTitle

            xbmc.sleep (250)
            media     = getCurrentMediaType()
            currTitle = getCurrentMediaTitle()            
            notifyEventPlayer ('onPlayBackStarted',media)
            currMedia = media

        def onPlayBackEnded(self): 
            global currMedia
            if (currMedia == "video") or (currMedia == 'tvshow'):
                time.sleep(debouncing_video)
                if not xbmc.Player().isPlaying():                                                                                                                                                                                       
                    notifyEventPlayer ('onPlayBackEnded',currMedia)

            if (currMedia == "audio"):
                time.sleep(debouncing_audio)
                if not xbmc.Player().isPlaying():
                    notifyEventPlayer ('onPlayBackEnded',currMedia)
            currMedia = 'none'                                                                                                                                                                                             
            currTitle = ""
            
        def onPlayBackStopped(self):
            global currMedia
            global currTitle
            notifyEventPlayer ('onPlayBackStopped',currMedia)     
            currTitle = ""  
            currMedia = "none"                                                                                                                                           
                                                                                                                                                                   
        def onPlayBackPaused(self): 
            global currMedia 
            notifyEventPlayer ('onPlayBackPaused',currMedia)                                                                                                                                                       
                      
        def onPlayBackResumed(self):
            global currMedia
            notifyEventPlayer ('onPlayBackResumed',currMedia)                                                                                                                                                      

class MyMonitor( xbmc.Monitor ):
        def __init__( self, *args, **kwargs ):
            xbmc.Monitor.__init__( self )
            debugLog ('Monitor init') 
            
        def onSettingsChanged( self ):
            #settings.start()
            #if not settings.reconnect:
            #  check_state()
            debugLog ('Monitor onSettingsChanged') 

        def onScreensaverDeactivated( self ):
            
            debugLog ('Monitor onScreensaverDeactivated') 
          
        def onScreensaverActivated( self ):    
            
            debugLog ('Monitor onScreensaverActivated') 

######################################################              
# Inicio del Addon
######################################################

if (str(settings.getSetting("debug_mod")) == "Yes"):
    debugMode = True
else:
    debugMode = False

debugLog ('Service start')
                                                                                                                                                                                                                                                                                                                                         
lastMedia   = "none"
lastMenu    = "none"
lastTitle   = ""
currMedia   = "none"
lastWindow  = 0

settingsOK = True
if (indigo_ip == "0.0.0.0") or (indigo_ip == ""):
    settingsOK = False
    errorLog ('Settings: Indigo IP address is empty')
if int(indigo_port <= 0):    
    settingsOK = False
    errorLog ('Settings: Indigo UDP Port is empty')

if (str(settings.getSetting("notification")) == "Yes"):
    if settingsOK == False:        
        xbmc.executebuiltin('Notification(%s, %s, %d, %s)'%(__addonname__,plugin_error, time1, __icon__))
    else:
        xbmc.executebuiltin('Notification(%s, %s, %d, %s)'%(__addonname__,plugin_start, time2, __icon__))

if settingsOK == False:
    errorLog ('indigoSendMsg. Exit. Settings are not Ok')
    sys.exit()

player  = MyPlayer() 
monitor = MyMonitor()           

#########################################################
# This socket uses DataGram. (UDP connectionless)
#########################################################

try:
    debugLog ('Creating socket')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    debugLog ('Socket created')
except socket.error:
    errorLog ('Socket error: ' + indigo_ip + ":" + indigo_port + ' ... ' + str(sys.exc_info()[1][1] ))
    pass

#########################################################
# Bucle principal
#########################################################

if sock != None:
    lastVolume, lastMuted = getCurrentVolume()
    notifyEventApp('start')
    notifyEventVolume(lastVolume,lastMuted)
    while(not xbmc.abortRequested):
        watchNavigation()
        xbmc.sleep(500)
    notifyEventApp('quit')
debugLog ('Addon quit')