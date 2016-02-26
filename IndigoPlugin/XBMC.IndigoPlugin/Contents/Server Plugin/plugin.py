#! /usr/bin/env python
# -*- coding: utf-8 -*-
######################################################################################

# http://wiki.xbmc.org/index.php?title=JSON-RPC_API/v6
# http://pastebin.com/9r1AMQ0H
# http://wiki.xbmc.org/?title=Add-ons

import os
import sys
import socket
import indigo
import math
import decimal
import datetime
import simplejson as json
import requests
from requests.auth import HTTPBasicAuth
from xml.etree import ElementTree as ET

class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        # Port
        self.listenPortDef = 8189
        self.listenPort    = 0

        self.apiVersion    = "2.0"
        self.localAddress  = ""
        # Pooling
        self.pollingInterval = 0
        self.requestID = 0

        # Flag buttonRequest is processing
        self.reqRunning = 0

        # create empty device list
        self.deviceList = {}

        self.sock = None
        self.socketBufferSize = 512
        self.socketStop       = False

    def __del__(self):
        indigo.PluginBase.__del__(self)

    ###################################################################
    # Plugin
    ###################################################################

    def deviceStartComm(self, device):
        self.debugLog(device.name + ": Starting device")
        propsAddress = ''

        if device.id not in self.deviceList:
            propsAddress = device.pluginProps["address"]
            propsAddress = propsAddress.strip()
            propsAddress = propsAddress.replace (' ','')
            self.deviceList[device.id] = {'ref':device,'address':propsAddress, 'lastTimeAlive':datetime.datetime.now()}

    def deviceStopComm(self,device):
        if device.id not in self.deviceList:
            return
        self.debugLog(device.name + ": Stoping device")
        del self.deviceList[device.id]

    def startup(self):
        self.loadPluginPrefs()
        self.debugLog(u"startup called")
        self.requestID = 0

        # Obtain local address.
        # This will identify a XBMC device running in same machine than Indigo
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("gmail.com",80))
        self.localAddress = s.getsockname()[0]
        s.close()

        self.debugLog("Local IP address: " + self.localAddress)

    def shutdown(self):
        self.debugLog(u"shutdown called")


    def deviceCreated(self, device):
        self.debugLog(u"Created device of type \"%s\"" % device.deviceTypeId)

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.debugLog(u"validating device Prefs called")
        ipAdr = valuesDict[u'address']
        if ipAdr.count('.') != 3:
            errorMsgDict = indigo.Dict()
            errorMsgDict[u'address'] = u"This needs to be a valid IP address."
            return (False, valuesDict, errorMsgDict)
        if self.validateAddress (ipAdr) == False:
            errorMsgDict = indigo.Dict()
            errorMsgDict[u'address'] = u"This needs to be a valid IP address."
            return (False, valuesDict, errorMsgDict)
        tcpPort = valuesDict[u'port']
        try:
            iPort = int(tcpPort)
            if iPort <= 0:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
                return (False, valuesDict, errorMsgDict)
        except Exception, e:
            errorMsgDict = indigo.Dict()
            errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
            return (False, valuesDict, errorMsgDict)
        if (valuesDict[u'useAuthentication']):
            if not(valuesDict[u'username']>""):
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'username'] = u"Must be filled."
                return (False, valuesDict, errorMsgDict)
            if not(valuesDict[u'password']>""):
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'password'] = u"Must be filled."
                return (False, valuesDict, errorMsgDict)
        return (True, valuesDict)

    def validatePrefsConfigUi(self, valuesDict):
        self.debugLog(u"validating Prefs called")
        tcpPort = valuesDict[u'listenPort']
        try:
            iPort = int(tcpPort)
            if iPort <= 0:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
                return (False, valuesDict, errorMsgDict)
        except Exception, e:
            errorMsgDict = indigo.Dict()
            errorMsgDict[u'port'] = u"This needs to be a valid TCP port."
            return (False, valuesDict, errorMsgDict)
        return (True, valuesDict)

    def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
        if userCancelled is False:
            indigo.server.log ("Device preferences were updated.")

    def closedPrefsConfigUi ( self, valuesDict, UserCancelled):
        #   If the user saves the preferences, reload the preferences
        if UserCancelled is False:
            indigo.server.log ("Preferences were updated, reloading Preferences...")
            self.loadPluginPrefs()

    def loadPluginPrefs(self):
        # set debug option
        if 'debugEnabled' in self.pluginPrefs:
            self.debug = self.pluginPrefs['debugEnabled']
        else:
            self.debug = False

        self.listenPort = 0

        if self.pluginPrefs.has_key("listenPort"):
            self.listenPort = int(self.pluginPrefs["listenPort"])
        if self.listenPort <= 0:
            self.listenPort = self.listenPortDef

    def validateAddress (self,value):
        try:
            socket.inet_aton(value)
        except socket.error:
            return False
        return True

    ###################################################################
    # Concurrent Thread. Socket
    ###################################################################

    def runConcurrentThread(self):

        self.debugLog(u"Starting listening socket on port " + str(self.listenPort))

        theXML  = ""
        xType   = ""
        xMenu   = ""
        xEvent  = ""
        xMedia  = ""
        xTitle  = ""
        xPlayer = ""
        xState  = ""
        xVolume = 0
        xMuted  = False
        indigoDevice = None

        try:

            self.sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("0.0.0.0",self.listenPort))
            self.sock.settimeout(1)
            # Get socket IP Address
            self.socketOpen = True
            self.debugLog(u"Socket is open")

        except socket.error:
            self.errorLog(u"Socket Setup Error: (%s) %s" % ( sys.exc_info()[1][0], sys.exc_info()[1][1] ))
        except Exception, e:
            self.errorLog (u"Error: " + str(e))
            pass

        try:
            while self.socketStop == False:
                indigoDevice = None
                theXML       = ""
                try:
                    # sock.recvfrom seems to only return complete log strings.  One log entry per return.
                    # Which is good, because log entries are not delimitted with any \n or \r characters.
                    # If responses were coming in with partial log entries and buffering was required
                    # to concatenate full strings it would be tricky to determine where one entry begins
                    # and the other ends.
                    theXML, addr = self.sock.recvfrom (int(self.socketBufferSize))
                    theXML       = str(theXML)
                    theXML       = theXML.strip()

                    addressFrom  = addr[0]
                    self.debugLog ("Socket. received: " + theXML + " from: " + str(addressFrom))

                    for xbmc in self.deviceList:
                        if self.deviceList[xbmc]['address'] == addressFrom:
                            choosen       = xbmc
                            indigoDevice  = self.deviceList[xbmc]['ref']
                            lastTimeAlive = self.deviceList[xbmc]['lastTimeAlive']
                            self.debugLog (u'Socket. Found XBMC device "' + indigoDevice.name + '" for address ' + addressFrom)
                    if indigoDevice == None:
                        self.debugLog (u"Socket. Not found XBMC device for address " + addressFrom)
                except socket.timeout:
                    # No data was received, socket timed out or bailed for some other reason
                    # self.plugin.debugLog(u"Socket Timeout")
                    pass
                except socket.error:
                    self.errorLog(u"Socket Setup Error: (%s) %s" % ( sys.exc_info()[1][0], sys.exc_info()[1][1] ))
                    pass
                except Exception,e:
                    self.errorLog (u"Error: " + str(e))
                    pass

                if (indigoDevice != None) and (theXML > ""):
                    theXML = '<?xml version="1.0"?>' + '<body>' + theXML + '</body>'
                    tree   = ET.fromstring (theXML)
                    xType  = tree.find('.//type').text

                    if (xType == 'app'):
                        xEvent = tree.find('.//event').text

                    if (xType == 'app') and (xEvent == 'quit'):
                        self.debugLog (u'Received going to quit from "' + indigoDevice.name)
                        xState = 'off'
                        self.updateDeviceState (indigoDevice,'menu'  ,'none')
                        self.updateDeviceState (indigoDevice,'media' ,'none')
                        self.updateDeviceState (indigoDevice,'player','stopped')
                        self.updateDeviceState (indigoDevice,'volume',0)
                        self.updateDeviceState (indigoDevice,'title' ,'')

                    else:
                        xState = 'on'

                        if xType == 'menu':
                            xMenu  = tree.find('.//menu').text
                            self.updateDeviceState (indigoDevice,'menu', xMenu)
                        if xType == 'volume':
                            xVolume = int (tree.find('.//volume').text)
                            xMuted  = tree.find('.//muted').text
                            xMuted  = xMuted.lower()
                            self.updateDeviceState (indigoDevice,'volume', xVolume)
                            if xMuted == 'true':
                                self.updateDeviceState (indigoDevice,'muted', 'Yes')
                            else:
                                self.updateDeviceState (indigoDevice,'muted', 'No')
                        if xType == 'player':
                            xTitle = tree.find('.//title').text
                            xMedia = tree.find('.//media').text
                            xEvent = tree.find('.//event').text

                            if (xEvent == 'onplaybackstarted') or (xEvent == 'onplaybackresumed'):
                                xPlayer = 'playing'
                            if xEvent == 'onplaybackpaused':
                                xPlayer = 'paused'
                            if (xEvent == 'onplaybackstopped') or (xEvent == 'onplaybackended'):
                                xPlayer = 'stopped'
                                xMedia  = 'none'
                                xTitle  = ''
                            self.updateDeviceState (indigoDevice,'title' ,xTitle)
                            self.updateDeviceState (indigoDevice,'media' ,xMedia)
                            self.updateDeviceState (indigoDevice,'player',xPlayer)
                        if xType == 'title':
                            xTitle = tree.find('.//title').text
                            if xTitle == '.':
                                xTitle = ''
                            self.updateDeviceState (indigoDevice,'title' ,xTitle)

                    self.deviceList[choosen]['lastTimeAlive'] = datetime.datetime.now()
                    if xState == 'on':
                        if indigoDevice.states["onOffState"] != True:
                            indigoDevice.updateStateOnServer("onOffState", True)
                            self.xbmcApplicationVersion(indigoDevice)
                    else:
                        indigo.server.log(u"\"%s\" %s" % (indigoDevice.name, " is off"))
                        indigoDevice.updateStateOnServer("onOffState", False)

                if (indigoDevice == None):
                    todayNow = datetime.datetime.now()
                    for xbmc in self.deviceList:

                        indigoDevice  = self.deviceList[xbmc]['ref']

                        if indigoDevice.states["onOffState"] == True:
                            lastTimeAlive = self.deviceList[xbmc]['lastTimeAlive']
                            secondsDiff = (todayNow-lastTimeAlive).seconds
                            if secondsDiff > 30:
                                indigoDevice.updateStateOnServer("onOffState", False)
                                self.debugLog (u'Socket. Switch off  "' + indigoDevice.name + '" by inactivity ')
                self.sleep(0.1)
            if self.sock != None:
                self.sock.close
                self.sock = None

        except self.StopThread:
            if self.sock != None:
                self.sock.close
                self.sock = None
            pass
            self.debugLog(u"Exited listening socket")
        except Exception, e:
            self.errorLog (u"Error: " + str(e))
            pass

    def stopConcurrentThread(self):
        self.socketStop = True
        self.stopThread = True
        self.debugLog(u"stopConcurrentThread called")

    ###################################################################
    # HTTP RPC Request against XBMC.
    ###################################################################

    def sendRpcRequest(self, device, method, params):
        # http://www.python-requests.org/en/latest/user/quickstart/
        r = None
        self.debugLog(device.name + ": sendRpcRequest")
        requestOK = False
        if device.pluginProps.has_key("useAuthentication") and device.pluginProps["useAuthentication"]:
            useAuth = True
            rUserName = device.pluginProps["username"]
            rPassword = device.pluginProps["password"]

        rUrl = "http://" + device.pluginProps["address"] + ":" + device.pluginProps["port"] + '/jsonrpc'
        rStatusCode = 0
        rHeaders = {'content-type': 'application/json'}

        self.requestID += 1
        if self.requestID > 9999:
            self.requestID = 1

        rJson = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self.requestID
            };

        try:
            rPayload = json.dumps(rJson)
            self.debugLog(device.name + ": Request content: %s" % rPayload)
            if useAuth == True:
                rAuth = HTTPBasicAuth(rUserName, rPassword)
                r = requests.post(url=rUrl, data=rPayload, headers=rHeaders, auth=rAuth, timeout=0.5)
            else:
                r = requests.post(url=rUrl, data=rPayload, headers=rHeaders, timeout=0.5)
            rStatusCode = r.status_code
        except Exception, e:
            lastError = str(e)
            self.errorLog(device.name + ": Request error : %s" % lastError)
            return False, r

        if rStatusCode == 200:
            if "error" in json.loads(r.content):
                self.errorLog(device.name + ": RPC API Error: %s" % r.content)
            else:
                requestOK = True
                self.debugLog(device.name + ": Response content: %s" % r.content)
        else:
            if rStatusCode == 401:
                self.errorLog(device.name + ": Kodi does not accept this. Please, check authorization settings for this Indigo device.")
            else:
                self.errorLog(device.name + ": Response status : %s" % rStatusCode)
        if requestOK == True:
            device.updateStateOnServer("onOffState", True)

        else:
            device.updateStateOnServer("onOffState", False)
        return requestOK, r

    def updateDeviceState(self,device,state,newValue):
        if (newValue != device.states[state]):
            device.updateStateOnServer(key=state, value=newValue)

    ###################################################################
    # Custom Action callbacks
    ###################################################################

    #https://github.com/CommandFusion/XBMC/blob/master/GUI/xbmcapp.js
    #http://wiki.xbmc.org/index.php?title=JSON-RPC_API/v6


    def xbmcApplicationStatusRequest (self,pluginAction,device):
        if self.sendRpcRequest  (device, "JSONRPC.Ping", {} ):
            device.updateStateOnServer("onOffState", True)
        else:
            device.updateStateOnServer("onOffState", False)
        pass


    def xbmcApplicationStart(self, pluginAction, device):
        if (device.pluginProps["address"] == self.localAddress) or (device.pluginProps["address"] == "127.0.0.1"):
            indigo.server.log(u"sent \"%s\" %s" % (device.name, "on"))
            self.debugLog(device.name + ": starting local.")
            try:
                if os.system("open -a Kodi") == 0:
                    return
            except Exception, e:    
                pass
            try:
                if os.system("open -a XBMC") == 0:
                    return
            except Exception,e:
                pass
            self.errorLog(device.name + ": Is Kodi/XBMC installed?")

        else:
            self.errorLog(device.name + ": This action only works if Kodi is running in the same machine than Indigo. Kodi address is: " + device.pluginProps["address"] + ". Indigo address is: " + self.localAddress)

    def xbmcApplicationQuit(self, pluginAction, device):
        playerState = device.states['player']
        if (playerState == "paused") or (playerState == "playing"):
            self.xbmcPlayerStop (pluginAction, device)
        menuState = device.states['menu']
        if (menuState == "none") or (menuState == "home"):
            pass
        else:
            self.xbmcInputHome  (pluginAction, device)

        actionwhenoff    = device.pluginProps["actionwhenoff"]

        if actionwhenoff == "nothing":
            pass
        elif actionwhenoff == "app.quit":
            indigo.server.log(u"sent \"%s\" %s" % (device.name, "off"))
            self.sendRpcRequest  (device, "Application.Quit", {} )
        elif actionwhenoff == "sys.shutdown":
            indigo.server.log(u"sent \"%s\" %s" % (device.name, "off and system shutdown"))
            self.sendRpcRequest  (device, "System.Shutdown", {} )
            device.updateStateOnServer("onOffState", False)
        #elif actionwhenoff == "relay.switchoff":
        #   relaytoswitchoff = int(device.pluginProps["relaytoswitchoff"])
        #   if relaytoswitchoff > 0:
        #       indigo.device.turnOff(relaytoswitchoff)
        else:
            indigo.server.log(u"sent \"%s\" %s" % (device.name, "off by default"))
            self.sendRpcRequest  (device, "Application.Quit", {} )
        device.updateStateOnServer("onOffState", False)

    def xbmcApplicationVersion(self, device):
        version_installed = []
        self.debugLog (u"query  \"%s\" %s" % (device.name, "version"))        
        status, r = self.sendRpcRequest  (device, "Application.GetProperties", {"properties": ["version"]} )
  
        if status:
            json_query = unicode(r.content, 'utf-8', errors='ignore')
            json_query = json.loads(json_query)
            version_installed = []
            if json_query.has_key('result') and json_query['result'].has_key('version'):
                version_installed  = json_query['result']['version']
                version_major  = version_installed['major']
                version_minor  = version_installed['minor']
                xbmcVersion = str(version_major) + '.' + str(version_minor)
                self.debugLog (u"\"%s\" version is %s" % (device.name, xbmcVersion))
                device.updateStateOnServer("xbmcVersion", xbmcVersion)
        return version_installed
        
        
    def xbmcSystemShutdown(self, pluginAction, device):
        indigo.server.log(u"sent \"%s\" %s" % (device.name, "shutdown"))
        self.sendRpcRequest  (device, "System.Shutdown", {} )
        device.updateStateOnServer("onOffState", False)

    def xbmcInputBack(self, pluginAction, device):
        self.sendRpcRequest  (device, "Input.Back", {} )

    def xbmcInputHome(self, pluginAction, device):
        self.sendRpcRequest  (device, "Input.Home",{} )

    def xbmcApplicationVolMuteOn(self, pluginAction, device):
        self.sendRpcRequest  (device, "Application.SetMute", {"mute": True} )
        self.updateDeviceState (device,'muted', 'Yes')

    def xbmcApplicationVolMuteOff(self, pluginAction, device):
        self.sendRpcRequest  (device, "Application.SetMute", {"mute": False} )
        self.updateDeviceState (device,'muted', 'No')

    def xbmcApplicationVolUp(self, pluginAction, device):
        volume = 75
        self.sendRpcRequest  (device, "Application.setVolume", {"volume": volume} )
        self.updateDeviceState (device,'volume',volume) 
        
    def xbmcApplicationVolDown(self, pluginAction, device):
        volume = 25
        self.sendRpcRequest  (device, "Application.setVolume", {"volume": volume}  )
        self.updateDeviceState (device,'volume',volume) 

    def xbmcPlayerPauseOn(self, pluginAction, device):
        xPlayerID = self.xbmcGetPlayerID(device)
        self.sendRpcRequest  (device, "Player.PlayPause", {"play": False, "playerid": xPlayerID} )

    def xbmcPlayerPauseOff(self, pluginAction, device):
        xPlayerID = self.xbmcGetPlayerID(device)
        self.sendRpcRequest  (device, "Player.PlayPause", {"play": True, "playerid": xPlayerID} )

    def xbmcPlayerStop(self, pluginAction, device):
        xPlayerID = self.xbmcGetPlayerID(device)
        self.sendRpcRequest  (device, "Player.Stop", {"playerid": xPlayerID} )

    def xbmcShowNotification (self,pluginAction,device):
        title       = self.substitute(pluginAction.props.get("title", ""))
        message     = self.substitute(pluginAction.props.get("message", ""))
        displaytime = self.substitute(pluginAction.props.get("displaytime", 0))
        self.xbmcShowNotificationApi (device,title,message,displaytime) 
            
    def xbmcShowNotificationSimple (self,pluginAction,device):
        message = self.substitute(pluginAction.props.get("message", ""))
        self.xbmcShowNotificationApi (device,"Indigo",message,0)    

    def xbmcShowNotificationApi (self,device,title,message,displaytime):        
        if displaytime > 0:
            msTime = int(displaytime) * 1000
            self.sendRpcRequest  (device, "GUI.ShowNotification", {"title": title, "message": message, "displaytime": msTime })
        else:
            self.sendRpcRequest  (device, "GUI.ShowNotification", {"title": title, "message": message })
        pass                
                    
    def xbmcGetPlayerID(self, device):
        #self.sendRpcRequest  (device, "Player.GetActivePlayers", {} )
        return 1

    def xbmcSetVolume (self, pluginAction, device):
        volume = int(self.substitute(pluginAction.props.get("volume", "0")))
        self.sendRpcRequest  (device, "Application.setVolume", {"volume": volume} ) 
        self.updateDeviceState (device,'volume',volume)     
        return

    def xbmcIncreaseVolume (self, pluginAction, device):
        volume = 0
        increment = int(self.substitute(pluginAction.props.get("increment", "0")))
        volume = int(device.states['volume'])
        volume += increment
        if volume > 100:
            volume = 100
        self.sendRpcRequest  (device, "Application.setVolume", {"volume": volume} )     
        self.updateDeviceState (device,'volume',volume) 
        pass
        return 

    def xbmcDecreaseVolume (self, pluginAction, device):
        volume = 0
        decrement = int(self.substitute(pluginAction.props.get("decrement", "0")))
        volume = int(device.states['volume'])
        volume -= decrement
        if volume < 0:
            volume = 1
        self.sendRpcRequest  (device, "Application.setVolume", {"volume": volume} ) 
        self.updateDeviceState (device,'volume',volume) 
        pass
        return

    def menuGetDevsRelay(self, filter, valuesDict, typeId, elemId):
        menuList = []
        for dev in indigo.devices.iter(filter="indigo.relay"):
            # Vamos a utilizar cualquier tipo de relay. No solo Piface
            #if self._devTypeIdIsMirrorOutput(dev.deviceTypeId):
            menuList.append((dev.id, dev.name))
        return menuList

    def menuClearSelDev(self, valuesDict, typeId, elemId):
        #valuesDict["relaytoswitchoff"] = 0
        return valuesDict

    def _devTypeIdIsRelayDevice(self, typeId):
        return true
        #return typeId in (u"PiFaceOutput", u"PiFaceInput")

    def actionControlDimmerRelay(self, pluginAction, device):
        # Relay ON ##
        if pluginAction.deviceAction == indigo.kDeviceAction.TurnOn:
            self.xbmcApplicationStart (pluginAction,device)

        # Relay OFF ##
        elif pluginAction.deviceAction == indigo.kDeviceAction.TurnOff:
            self.xbmcApplicationQuit (pluginAction,device)

        elif pluginAction.deviceAction == indigo.kDeviceAction.Toggle:
            if device.states["onOffState"]:
                self.xbmcApplicationQuit (pluginAction,device)
            else:
                self.xbmcApplicationStart (pluginAction,device)

        # Relay Status Request ##
        elif pluginAction.deviceAction == indigo.kDeviceAction.RequestStatus:
            indigo.server.log(u"sent \"%s\" %s" % (device.name, "status request"))
            self.xbmcApplicationStatusRequest (pluginAction,device)
        #   if not(self.sensorUpdate (device)):
        #       self.errorLog(u"\"%s\" %s" % (device.name, "status request failed"))
