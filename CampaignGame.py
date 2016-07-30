#Campaign Game
#going to try first in python, we'll see how that goes

from Tkinter import *
import tkMessageBox
from PIL import Image, ImageTk
import os
import random
import time
import math
import sys

#global variables fro tracking players and turns
player = 1                  #keeps track of whose turn it is. indexed at 1
numPlayers = 2
currentDate = 0
players = {}            #dictionaries of class instances of players and states
states = {}
calendarOfContests = [('Iowa' , 2),('New Hampshire' , 4) ,('Nevada',7), ('South Carolina',8),('Minnesota',9),('Alabama' , 9), ('Arkansas', 9), ('Colorado', 9), ('Georgia', 9), ('Massachusetts', 9), ('North Dakota', 9), ('Oklahoma', 9), ('Tennessee', 9), ('Texas', 9), ('Vermont', 9), ('Virginia', 9), ('Kansas', 10), ('Kentucky', 10), ('Louisiana', 10), ('Maine', 10), ('Nebraska', 10), ('Hawaii', 10), ('Michigan', 10), ('Mississippi', 10), ('Wyoming', 11), ('Florida', 11), ('Illinois' , 11), ('Missouri', 11), ('North Carolina', 11), ('Ohio', 11), ('Arizona', 12), ('Idaho', 12), ('Utah', 12),('Alaska', 13), ('Washington', 13), ('Wisconsin', 14), ('New Jersey', 15), ('New York', 15), ('Connecticut', 15), ('Delaware', 15), ('Maryland', 15), ('Pennsylvania', 15), ('Rhode Island', 15), ('Indiana', 16), ('West Virginia', 16), ('Oregon', 17), ('California', 19), ('Montana', 19), ('New Mexico', 19), ('South Dakota', 19)]#, ('DC', 20)]
playerColors = [(255,0,0), (0,0,255), (0,255,0), (128,0,128)]
eventOfTheWeek = 0
issueNames = ['Immigration', 'Gun Control', 'Jobs', 'Tax Reform', 'Education']
pastElections = {}          #stores the winner of each elections thats happened

class Player:
    def __init__(self, player):
        self.name = player
        self.resources = [80, 100000]
        self.positions = []
        self.delegateCount = 0
        self.momentum = 0

    def setPositions(self, positions):
        self.positions = positions

class State:
    def __init__(self, stateName, positions):
        self.name = stateName
        self.positions = positions
        self.opinions = []
        self.support = []
        self.organizations = []
        self.districts = []

    def updateSupport(self):        
        newSupport = []
        global numPlayers
        for j in range(numPlayers):
            newSupport.append(0)
        for i in range(numPlayers): 
            for district in self.districts:
                newSupport[i] += district.support[i] * district.population
        self.support = newSupport
        return

    def setOrganization(self, playerIndex, organizations):
        try:
            self.organizations[playerIndex] = organizations
        except IndexError:
            self.organizations.append(organizations)

    def setOpinions(self, opinionList):
        self.opinions = opinionList

    def addDistrict(self, newDistrict):
        self.districts.append(newDistrict)

class District:
    def __init__(self, name, pop, parent):
        self.name = name
        self.population = int(pop)                     #in terms of congressional delgates
        self.state = parent
        self.opinions = []
        self.support = []
        self.campaigningThisTurn = []
        self.adsThisTurn = []

    def setSupport(self, playerIndex, s):
        try:
            self.support[playerIndex] += s
        except IndexError:
            self.support.append(s)

    def setOpinions(self, opinionList):
        self.opinions = opinionList

    def setCampaigningThisTurn(self, playerIndex, campaigningThisTurn):
        try: 
            self.campaigningThisTurn[playerIndex] = campaigningThisTurn
        except IndexError:
            self.campaigningThisTurn.append(campaigningThisTurn)

    def setAdsThisTurn(self, playerIndex, ads):
        try:
            self.adsThisTurn[playerIndex] = ads
        except IndexError:
            self.adsThisTurn.append(ads)


def main():
    setUpStates()
    setUpGame()
    while True:
        createNationalMap()

def setUpGame():        #this will set up the basic parameters of the game, or have the option to load a previously saved game.  
    setUpWindow = Tk()

    w = 200
    h = 200
    ws = setUpWindow.winfo_screenwidth() # width of the screen
    hs = setUpWindow.winfo_screenheight() # height of the screen
    # calculate x and y coordinates for the Tk root window
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)
    setUpWindow.geometry('%dx%d+%d+%d' % (w, h, x, y))

    mode = IntVar()

    noIssueMode = Radiobutton(setUpWindow, text = "No Issues Mode", variable = mode, value = 1)
    noIssueMode.pack()
    issueMode = Radiobutton(setUpWindow, text = "Issues Mode", variable = mode, value = 2)
    issueMode.pack()

    startGame = Button(setUpWindow, text = 'Start Game', command = lambda:setUpPlayers(numP.get(), setUpWindow, mode.get()))
    numP = Scale(setUpWindow, label = 'Number of Players', orient = HORIZONTAL, from_= 2, to_ = 10)

    startGame.pack()
    numP.pack()
    setUpWindow.mainloop()

def setUpStates(): 
    statesList = open('statesPositions.txt', 'r')
    global states
    for line in statesList:
        l = line.split(',')
        if l[0] != "State Name":
            newState = State(l[0], l[1:])
            states[newState.name] = newState

    districts = open('districts.txt' , 'r')
    currentStateName = ''
    for line in districts:
        l = line.split(',')
        currentStateName = l[0]
        newDistrict = District(l[1].strip(), int(l[2].strip()) * 3, l[0])
        currentState = states[currentStateName]
        currentState.addDistrict(newDistrict)


def setUpPlayers(numP, setUpWindow, mode):
    setUpWindow.destroy()
    global numPlayers
    global players
    global states
    numPlayers = numP
    for i in range(numPlayers):
        newPlayer = Player(i + 1)
        players[i + 1] = newPlayer
        for state in states:
            states[state].setOrganization(i,0)
            for district in states[state].districts:
                district.setSupport(i, 0)
                district.setCampaigningThisTurn(i, 0)
                district.setAdsThisTurn(i, 0)
    for state in states:
        states[state].updateSupport()

    if mode == 1:
        for person in players:
            players[person].setPositions([0,0,0,0,0])
        calculateStateOpinions()
    else:
        setUpPlayer()

def setUpPlayer():      #this function will create the screen to set up a candidate initially. 
    setUpPlayerWindow = Tk()
    setUpPlayerWindow.wm_title("Choose Positions for player " + str(player))
    w = 400 # width for the Tk root
    h = 400 # height for the Tk root

    # get screen width and height
    ws = setUpPlayerWindow.winfo_screenwidth() # width of the screen
    hs = setUpPlayerWindow.winfo_screenheight() # height of the screen

    # calculate x and y coordinates for the Tk root window
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)

    # set the dimensions of the screen 
    # and where it is placed
    setUpPlayerWindow.geometry('%dx%d+%d+%d' % (w, h, x, y))

    issueLowRange = -10
    issueHighRange = 10

    issue1 = Scale(setUpPlayerWindow, from_ = issueLowRange, to_ = issueHighRange, label = "Issue Name 1", orient = HORIZONTAL, length = 300)
    issue2 = Scale(setUpPlayerWindow, from_ = issueLowRange, to_ = issueHighRange, label = "Issue Name 2", orient = HORIZONTAL, length = 300)
    issue3 = Scale(setUpPlayerWindow, from_ = issueLowRange, to_ = issueHighRange, label = "Issue Name 3", orient = HORIZONTAL, length = 300)
    issue4 = Scale(setUpPlayerWindow, from_ = issueLowRange, to_ = issueHighRange, label = "Issue Name 4", orient = HORIZONTAL, length = 300)
    issue5 = Scale(setUpPlayerWindow, from_ = issueLowRange, to_ = issueHighRange, label = "Issue Name 5", orient = HORIZONTAL, length = 300)

    issue1.pack()
    issue2.pack()
    issue3.pack()
    issue4.pack()
    issue5.pack()

    endChoose = Button(setUpPlayerWindow, text = 'Done Choosing Positions', command = lambda: setPositions(issue1.get(), issue2.get(), issue3.get(), issue4.get(), issue5.get(), setUpPlayerWindow))
    endChoose.pack()
    setUpPlayerWindow.mainloop()

def setPositions(issue1, issue2, issue3, issue4, issue5, setUpPlayerWindow):
    setUpPlayerWindow.destroy()
    global players
    global numPlayers
    global player
    person = players[player]
    person.setPositions([issue1, issue2, issue3, issue4, issue5])
    if player < numPlayers:
        player += 1
        setUpPlayer()
    else:
        player = 1
        calculateStateOpinions()
    
def paintNationalMap(natMapImage):         #his function will repaint the national map to show who is leading in each state
    global states
    global playerColors
    global calendarOfContests
    global currentDate
    global pastElections

    pixels = natMapImage.load()
    pixelList = open('pixelList.txt' , 'r')

    stateLeaders = {}
    for state in states:
        try:
            for stateTime in calendarOfContests:
                if stateTime[1] < currentDate and stateTime[0] == state:
                    stateLeaders[state] = pastElections[state] - 1
                elif stateTime[0] == state:
                    support = states[state].support
                    if max(support) > 0:
                        stateLeaders[state] = support.index(max(support))
        except KeyError:
            pass
    for line in pixelList:
        l = line.split(',')
        x = int(l[0])
        y = int(l[1])
        state = l[2].strip()
        try:
            leader = stateLeaders[state]
            color = playerColors[leader]
            pixels[(x,y)] = color
        except KeyError:
            pass
    return natMapImage

def createNationalMap():    #creates the main national map screen. This will be the main screen of the game, where the turn starts and ends.
    window = Tk()
    mapWindow = PanedWindow(window)
    global eventOfTheWeek
    global issueNames

    global player
    window.wm_title("Player " + str(player) + "\'s Turn")
    fundraising = 0

    natMapImage = Image.open("nationalMap.jpg")
    natMapIamge = paintNationalMap(natMapImage)
    natMapImg = ImageTk.PhotoImage(natMapImage)

    menuBar = Menu(window)
    mainMenu = Menu(menuBar, tearoff = 0)
    mainMenu.add_command(label = "Save", command = saveGame)
    mainMenu.add_command(label = 'Load', command = loadGame)
    menuBar.add_cascade(label = 'Main Menu' , menu = mainMenu)
    window.config(menu = menuBar)

    calendarPane = PanedWindow(mapWindow, orient = VERTICAL)
    mapWindow.add(calendarPane)
    calendarTitle = Label(calendarPane, text = "Calendar of Primaries:", anchor = N)
    current = Label(calendarPane, text = 'Week of the campaign number ' + str(currentDate), anchor = N)
    
    calendarPane.add(calendarTitle)
    calendarPane.add(current)

    k = 0
    j=0
    while k <= 22 and j < len(calendarOfContests):     #display the next 22 contests to fill the left bar
        nextContest = calendarOfContests[j]
        name = nextContest[0]
        date = nextContest[1]
        if date >= currentDate:
            nextContestLabel = Label(calendarPane, text = name + " on week " + str(date))
            calendarPane.add(nextContestLabel)
            k += 1
            j+=1
        else:
            j+=1
    placeHolderLabel4 = Label(calendarPane, anchor = N)
    calendarPane.add(placeHolderLabel4)

    natMap = Label(mapWindow, image = natMapImg)
    mapWindow.add(natMap)   

    resourcePane = PanedWindow(mapWindow, orient = VERTICAL)
    mapWindow.add(resourcePane)

    global players
    resources = players[player].resources
    moneyVar = StringVar()
    moneyVar.set('available money: %s' %(resources[1]))
    timeLabel = Label(resourcePane, text = "available candidate time: " + str(resources[0]), anchor = N)
    moneyLabel = Label(resourcePane, textvariable = moneyVar, anchor = N)

    global playerColors
    for person in players:
        color = playerColors[person - 1]
        color = '#%02x%02x%02x' % color
        delegateLabel = Label(resourcePane, text = 'Player ' + str(players[person].name) + ' has ' + str(players[person].delegateCount) + ' delegates', bg = color)
        resourcePane.add(delegateLabel)

    momentumLabel = Label(resourcePane, text = 'Your Current Momentum is: ' + str(round(players[player].momentum, 0)))
    resourcePane.add(momentumLabel)

    placeHolderLabel3 = Label(resourcePane, anchor = S)
    resourcePane.add(placeHolderLabel3)

    placeHolderLabel = Label(resourcePane, anchor = S)  
    placeHolderLabel2 = Label(resourcePane, anchor = S)
    endTurnButton = Button(resourcePane, text = 'End Turn', command = lambda : endTurn(window, fundraisingScale.get()), anchor = S)

    fundraisingLabel = Label(resourcePane, text = 'How much time do you want \n to spend fundraising this week?')
    fundraisingScale = Scale(resourcePane, orient = HORIZONTAL, from_ = 0, to = resources[0], variable = fundraising)

    eventOfTheWeekLabel = Label(resourcePane, text = 'At the top of the news \n cycle this week: %s' %(issueNames[eventOfTheWeek]))

    resourcePane.add(timeLabel)
    resourcePane.add(moneyLabel)
    resourcePane.add(placeHolderLabel)
    resourcePane.add(eventOfTheWeekLabel)
    resourcePane.add(placeHolderLabel2)
    resourcePane.add(fundraisingLabel)
    resourcePane.add(fundraisingScale)
    resourcePane.add(endTurnButton)

    natMap.image = natMapImage
    mapWindow.pack()
    #natMap.bind('<Enter>', showStats)

    center(window)
    natMap.bind('<Button-1>', zoomToState)
    window.protocol("WM_DELETE_WINDOW", exitGame)
    window.mainloop()
        
def center(toplevel):           #copied from an answer by user Wayne Werner on stackoverflow
    toplevel.update_idletasks()
    w = toplevel.winfo_screenwidth()
    h = toplevel.winfo_screenheight()
    size = tuple(int(_) for _ in toplevel.geometry().split('+')[0].split('x'))
    x = w/2 - size[0]/2
    y = h/2 - size[1]/2
    toplevel.geometry("%dx%d+%d+%d" % (size + (x, y)))

def showStats(event):   #this will bring up a window with a quick overview of the state of the state
    xLoc = event.x
    yLoc = event.y
    w = 250
    h = 150
    pixelList = open('pixelList.txt' , 'r')
    global states
    stateName = '404'
    for line in pixelList:
        l = line.split(',')
        if xLoc == int(l[0]) and yLoc == int(l[1]):
            try:
                stateName = l[2].strip()
                currentState = states[stateName]
                stateWindow = Tk()
                stateWindow.wm_title(stateName)
                stats = currentState.positions
                opinion = currentState.opinions[player - 1]
                opinionLabel = Label(stateWindow, text = "Opinion of you: " + str(opinion))
                opinionLabel.pack()
                for i in range(len(stats)):
                    issue = Label(stateWindow, text = "Position on issue " + str(i) + ": " + str(stats[i]))
                    issue.pack()
                stateWindow.geometry('%dx%d+%d+%d' % (w, h, xLoc, yLoc))
                stateWindow.mainloop()
            except ValueError:
                tkMessageBox.showerror("state error","That's not a state")

def zoomToState(event):  #this will bring up the state window, seperate from the main window
    xLoc = event.x
    yLoc = event.y

    pixelList = open('pixelList.txt' , 'r')
    global issueNames
    global player
    global numPlayers
    global states 
    global players

    resources = players[player].resources
    stateName = '404'
    for line in pixelList:
        l = line.split(',')
        if xLoc == int(l[0]) and yLoc == int(l[1]):
            try:
                stateName = l[2].strip()
                stateWindow = Toplevel()
                path = os.getcwd()
                statePane = PanedWindow(stateWindow, orient = HORIZONTAL)
                leftPane = PanedWindow(statePane, orient = VERTICAL)
                stateWindow.wm_title(stateName)
                stats = states[stateName].positions
                #opinion = states[stateName].opinions[player - 1]
                #opinionLabel = Label(leftPane, text = "Opinion of you: " + str(opinion))
                #leftPane.add(opinionLabel)

                for person in range(numPlayers):
                    supportLabel = Label(leftPane, text = 'Current Level of Support for Player ' + str(person+1) + ': ' + str(states[stateName].support[person]))
                    leftPane.add(supportLabel)

                districts = open('districts.txt' , 'r')
                delegates = 0
                for line in districts:
                    l = line.split(',')
                    if l[0].strip() == stateName:
                        delegates += int(l[2].strip()) * 3
                delegatesLabel = Label(leftPane, text = 'This State has ' + str(delegates) + " delegates")
                leftPane.add(delegatesLabel)

                for district in states[stateName].districts:
                    districtDelegatesLabel = Label(leftPane, text = district.name + " District has " + str(int(district.population)) + " delegates")
                    leftPane.add(districtDelegatesLabel)
                    for person in range(numPlayers):
                        districtSupportLabel = Label(leftPane, text = "Current Support for player " + str(person + 1) + "in this district: " + str(district.support[person]))
                        leftPane.add(districtSupportLabel)

                '''eventOfTheWeekLabel = Label(leftPane, text = 'At the top of the news \n cycle this week: %s' %(issueNames[eventOfTheWeek]))
                leftPane.add(eventOfTheWeekLabel)
                for i in range(len(stats)):
                    issue = Label(leftPane, text = "Position on " + issueNames[i] + ": " + str(stats[i]), anchor = N)
                    leftPane.add(issue)'''
                placeHolderLabel = Label(leftPane)
                leftPane.add(placeHolderLabel)
                statePane.add(leftPane)

                stateImage = Image.open(path + '\\stateDistricts\\' + stateName + '.jpeg')
                stateImg = ImageTk.PhotoImage(stateImage)

                stateImageLabel = Label(statePane, image = stateImg)
                statePane.add(stateImageLabel)

                currentOrg = states[stateName].organizations[player-1]

                rightPane = PanedWindow(stateWindow, orient = VERTICAL)
                moreRightPane = PanedWindow(stateWindow, orient = VERTICAL)
                if currentOrg == 0:      #if the player has not yet on the ballot in the state
                    ballotLabel = Label(rightPane, text = 'Cost to get on the ballot ' + stateName + ': $10,000')
                    ballotButton = Button(rightPane, text = 'Get on the Ballot', command = lambda : getOnBallot(player, stateName, 10000, stateWindow, event))
                    rightPane.add(ballotLabel)
                    rightPane.add(ballotButton)

                if currentOrg == 1: #to establish a field office in the state
                    establishLabel = Label(rightPane, text = 'Cost to establish a field office in ' + stateName + ': $10,000')
                    establishButton = Button(rightPane, text = 'Build field office', command = lambda : getOnBallot(player, stateName, 10000, stateWindow, event))
                    rightPane.add(establishLabel)
                    rightPane.add(establishButton)

                if currentOrg > 1:
                    buildLabel = Label(rightPane, text = 'Cost to further develop your organization in ' + stateName + ':' + str(10000 * currentOrg))
                    buildButton = Button(rightPane, text = 'Build More Organization', command = lambda : getOnBallot(player, stateName, 10000 * currentOrg, stateWindow, event))
                    rightPane.add(buildLabel)
                    rightPane.add(buildButton)

                orgLabel = Label(rightPane, text = 'Your current organization level in this state: ' + str(currentOrg), anchor = N)
                rightPane.add(orgLabel)

                districts = open("districts.txt", 'r')
                districtTitleLabel = Label(rightPane, text = "State Districts: ")
                rightPane.add(districtTitleLabel)
                addBuys = []
                campaingingTime = []
                allocatedTime = 0
                j = 0
                for line in districts:
                    l = line.split(',')
                    if l[0] == stateName:
                        if j < 4:
                            districtLabel = Label(rightPane, text = l[1].strip())
                            addBuySlider = Scale(rightPane, label = "Add buys for this district", from_ = 0, to = resources[1], resolution = 1000, orient = HORIZONTAL)
                            campaigningSlider = Scale(rightPane, label = "Time Campaigning in this District", from_ = 0, to = resources[0], orient = HORIZONTAL)
                            districtAllocatedTime = states[stateName].districts[j].campaigningThisTurn[player - 1]
                            j += 1
                            campaigningSlider.set(districtAllocatedTime)
                            allocatedTime += districtAllocatedTime

                            addBuys.append(addBuySlider)
                            campaingingTime.append(campaigningSlider)
                            rightPane.add(districtLabel)
                            rightPane.add(campaigningSlider)
                            rightPane.add(addBuySlider)
                        else: 
                            districtLabel = Label(moreRightPane, text = l[1].strip())
                            addBuySlider = Scale(moreRightPane, label = "Add buys for this district", from_ = 0, to = resources[1], resolution = 1000, orient = HORIZONTAL)
                            campaigningSlider = Scale(moreRightPane, label = "Time Campaigning in this District", from_ = 0, to = resources[0], orient = HORIZONTAL)
                            districtAllocatedTime = states[stateName].districts[j].campaigningThisTurn[player - 1]
                            j += 1
                            campaigningSlider.set(districtAllocatedTime)
                            allocatedTime += districtAllocatedTime

                            addBuys.append(addBuySlider)
                            campaingingTime.append(campaigningSlider)
                            moreRightPane.add(districtLabel)
                            moreRightPane.add(campaigningSlider)
                            moreRightPane.add(addBuySlider)

                doneButton = Button(rightPane, text = "Done with State", command = lambda : backToMap(event.widget.winfo_toplevel(), campaingingTime, stateName, allocatedTime, addBuys), anchor = S)
                rightPane.add(doneButton)

                statePane.add(rightPane)
                if j > 4:
                    statePane.add(moreRightPane)
                statePane.pack()

                center(stateWindow)
                stateWindow.mainloop()
            except KeyError:
                tkMessageBox.showerror("state error","That's not a state")
                stateWindow.destroy()

def getOnBallot(player, stateName, cost, window, event):
    window.destroy()
    global calendarOfContests
    global currentDate
    global states
    global players
    
    currentOrg = states[stateName].organizations[player-1]
    for state in calendarOfContests:
        if stateName == state[0]:
            contestDate = state[1]

    if currentOrg == 0:
        if players[player].resources[1] - int(cost) >= 0 and currentDate < (contestDate - 1): 
            states[stateName].organizations[player-1] = 1
            players[player].resources[1] = players[player].resources[1] - int(cost)
            zoomToState(event)
        elif players[player].resources[1] - int(cost) >= 0:
            tkMessageBox.showerror("Timing Error", "Too late to get on the Ballot here")
        elif currentDate < (contestDate - 1):
            tkMessageBox.showerror("Money Error", "You Don't have enough money to get on the ballot")
    else:
        if players[player].resources[1] - int(cost) >= 0: 
            states[stateName].organizations[player-1] += 1
            players[player].resources[1] = players[player].resources[1] - int(cost)
            zoomToState(event)
        else:
            if currentOrg ==1:
                tkMessageBox.showerror("Money Error", "You Don't have enough money to build an office here")
            if currentOrg > 1:
                tkMessageBox.showerror("Money Error", "You Don't have enough money to further build your team here")

def backToMap(window, campaingingTime, stateName, allocatedTime, addBuys):
    global player
    global states
    global players

    totalAdCosts = 0
    totalTime = 0
    for slider in addBuys:
        totalAdCosts += slider.get()
    for slider in campaingingTime:
        totalTime += slider.get()

    if totalAdCosts > players[player].resources[1]:
        tkMessageBox.showerror("Money Error", "You don't have enough money for those ad buys")
    elif totalTime > players[player].resources[0]:
        tkMessageBox.showerror("Time Error", "You don't have enough time for all that campaigning")
    else:
        players[player].resources[1] -= totalAdCosts
        players[player].resources[0] -= totalTime
        districtList = open("districts.txt", 'r')
        i = 0
        for line in districtList:
            l = line.split(',')
            if l[0] == stateName:
                districtName = l[1].strip()
                currentState = states[stateName]
                for district in currentState.districts:
                    if district.name == districtName:
                        district.setAdsThisTurn(player - 1, addBuys[i].get())
                        district.setCampaigningThisTurn(player - 1, campaingingTime[i].get())
                i += 1

    window.destroy()
    createNationalMap()

def endTurn(window, fundraising):
    top = window.winfo_toplevel()
    top.destroy()
    global player
    global numPlayers
    global currentDate
    global eventOfTheWeek
    global states
    global players

    calcEndTurn(fundraising)

    if player < numPlayers:
        player += 1
    else: 
        currentDate += 1
        calculateStateOpinions()
        decideContests()
        player = 1
        eventOfTheWeek = random.randint(0,4)
        for state in states:
            for district in states[state].districts:
                for person in players:
                    district.setCampaigningThisTurn(person - 1, 0)
                    district.setAdsThisTurn(person - 1, 0)
    if currentDate <= 20:
        return
    else:
        winner = 0
        mostDelegates = 0
        for person in players:
            if players[person].delegateCount > mostDelegates:
                winner = person
                mostDelegates = players[person].delegateCount
        tkMessageBox.showinfo("Winner", "The Winner is: Player " + str(winner))
        exit()

def calcEndTurn(fundraising):      #this will calculate the new resources available to the player
    global player
    global playerResources
    global states

    resources = players[player].resources

    #time
    resources[0] = 80
    #money: remaining + fundraising + baseline + momentum + from states organization
    localFundraising = 0
    for state in states:
        localFundraising += states[state].organizations[player - 1] * 1000 + states[state].organizations[player - 1] * (states[state].support[player - 1]/60) * 1000 - states[state].organizations[player - 1] * 3000
    localFundraising = round(localFundraising)
    resources[1] = resources[1] + fundraising * 2000 + 20000 + localFundraising
    players[player].momentum = players[player].momentum * 2 ** (-1)

def calculateStateOpinions():       #this function will calculate the opinion of each player in each state
    global currentDate
    global states
    global players
    global calendarOfContests

    if currentDate == 0:       #calculate the inital position of the opinions
        for state in states:
            opinionList = []
            for person in players:
                opinion = 0
                for i in range(len(states[state].positions)):
                    opinion += int(states[state].positions[i].strip()) * players[person].positions[i]     #the inital opinion is based on the differences on the issues between the state and the candidate.
                    opinionList.append(opinion)
                states[state].setOpinions(opinionList)
        createNationalMap()

    else:               #each turn after that the new support is calculated. a player must be on the ballot (organization level 1) to get any support
        for i in range(len(players)):
            for state in states:
                org = states[state].organizations[i]
                for district in states[state].districts:
                    for date in calendarOfContests:             #in the 2 weeks before the election campaining is more effective
                        mult = 1
                        if date[0] == state and date[1] == currentDate - 1:
                            mult = 2
                        elif date[0] == state and date[1] == currentDate:
                            mult = 1.5
                    campaingingTime = district.campaigningThisTurn[i]
                    adBuy = district.adsThisTurn[i]
                    adsTotal = sum(district.adsThisTurn)
                    support = (campaingingTime + org + float(adBuy) / float(adsTotal + 1) * (adsTotal / 100.0) ** (1.1/2.0)) * (1 + float(players[i + 1].momentum) / 100.0) * mult          #the plus 1 is to avoid dividing by 0 when there is no advertising in a state
                    support = round(support)
                    district.setSupport(i, support)
                states[state].updateSupport()

        #print states["Iowa"].support

def decideContests():
    global currentDate
    global calendarOfContests
    global states
    global numPlayers
    global players
    global pastElections

    resultsWindow = Tk()
    j = 0
    for state in calendarOfContests:
        if state[1] + 1 == currentDate:
            j += 1
            stateName = state[0]
            orgs = states[stateName].organizations
            stateDelegates = 0
            stateVotes = []
            for i in range(numPlayers):
                stateVotes.append(0)
            for district in states[stateName].districts:
                districtDelegates = (district.population * 2) / 3
                stateDelegates += district.population - districtDelegates
                winner = 0
                mostVotes = 0
                for i in range(numPlayers):
                    if orgs[i] > 0:
                        votes = random.gauss(district.support[i], 15)
                        if votes < 0:
                            votes = 1
                        if votes > mostVotes:
                            winner = i + 1
                            mostVotes = votes
                        elif votes == mostVotes:
                            winner = random.randint(1, numPlayers)
                        stateVotes[i] += votes * district.population
                    else:
                        votes = 0

                if winner == 0:
                    winner = random.randint(1, numPlayers)
                    stateVotes[winner - 1] += 1
                districtResultsLabel = Label(resultsWindow, text = district.name + " district in " + stateName + " is won by player " + str(winner) + " giving " + str(districtDelegates) + " delegates")
                districtResultsLabel.pack()
                players[winner].delegateCount += districtDelegates
                players[winner].momentum += 3

            stateWinner = stateVotes.index(max(stateVotes)) + 1
            stateMostVotes = max(stateVotes)
            players[stateWinner].delegateCount += stateDelegates
            players[stateWinner].momentum += 10

            pastElections[stateName] = stateWinner
            print stateName, stateWinner, stateDelegates
            resultsLabel = Label(resultsWindow, text = stateName + " is won by player " + str(winner) + " giving " + str(stateDelegates) + " delegates")
            resultsLabel.pack()
    if j >= 1:
        center(resultsWindow)
        resultsWindow.mainloop()
    else:
        resultsWindow.destroy()

def saveGame():
    pass

def loadGame():
    pass

def exitGame():
    sys.exit()

def returnColor(event):
    natMap = event.widget

    natMapImage = Image.open("nationalMap.png")
    mapPix = natMapImage.load()

    print mapPix[event.x, event.y]

#this only was used for game set up (creating the pixel list). It won't be used in normal game function.
def defineState(event):     #when a state is clicked on all this should find all the pixels contigous(no black lines) to the one clicked, then prompt for the state's name, and create a database assigning each pixel to a state. 
    pixelList = open('pixelList.txt' , 'a')
    natMapImage = Image.open("nationalMap.png")
    mapPix = natMapImage.load()

    initPoint = (event.x, event.y)
    allPoints = [initPoint]
    endPoints = []      #because its he list of points we should have at the end, not the points that are ends
    while len(allPoints) > 0:
        for point in allPoints:
            newLeft = (point[0] - 1, point[1])
            newRight = (point[0] + 1, point[1])
            newUp = (point[0], point[1] - 1)
            newDown = (point[0], point[1] + 1)
            allPoints.remove(point)
            endPoints.append(point)
            if newLeft not in allPoints and mapPix[newLeft] == 31 and newLeft not in endPoints:
                allPoints.append(newLeft)
                mapPix[newLeft] = 0
            if newRight not in allPoints and mapPix[newRight] == 31 and newRight not in endPoints:
                allPoints.append(newRight)
                mapPix[newRight] = 0
            if newUp not in allPoints and mapPix[newUp] == 31 and newUp not in endPoints:
                allPoints.append(newUp)
                mapPix[newUp] = 0
            if newDown not in allPoints and mapPix[newDown] == 31 and newDown not in endPoints:
                allPoints.append(newDown)
                mapPix[newDown] = 0
    natMapImage.show()
    
    stateName = raw_input("what state")
    for point in endPoints:
        pixelList.write('%s,%s,%s \n' %(point[0], point[1], stateName))

main()