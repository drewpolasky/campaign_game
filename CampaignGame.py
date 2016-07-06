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
playerPositions = {}        #dictonary where values are lists of the players positions on issues
player = 1                  #keeps track of whose turn it is. indexed at 1
numPlayers = 2
currentDate = 0
playerResources = {} 
statePositions = {}
calendarOfContests = [('Iowa' , 2),('New Hampshire' , 4) ,('Nevada',7), ('South Carolina',7),('Minnesota',9),('Alabama' , 9), ('Arkansas', 9), ('Colorado', 9), ('Georgia', 9), ('Massachusetts', 9), ('North Dakota', 9), ('Oklahoma', 9), ('Tennessee', 9), ('Texas', 9), ('Vermont', 9), ('Virginia', 9), ('Kansas', 10), ('Kentucky', 10), ('Louisiana', 10), ('Maine', 10), ('Nebraska', 10), ('Hawaii', 10), ('Michigan', 10), ('Mississippi', 10), ('Wyoming', 11), ('Florida', 11), ('Illinois' , 11), ('Missouri', 11), ('North Carolina', 11), ('Ohio', 11), ('Arizona', 12), ('Idaho', 12), ('Utah', 12), ('Washington', 13), ('New York', 15), ('Connecticut', 15), ('Delaware', 15), ('Maryland', 15), ('Pennsylvania', 15), ('Rhode Island', 15), ('Indiana', 16), ('West Virginia', 16), ('Oregon', 17), ('California', 19), ('Montana', 19), ('New Mexico', 19), ('South Dakota', 19)]#, ('DC', 20)]
stateOpinions = {}
playerColors = ['red', 'blue','purple', 'green', 'orange', 'brown', 'cyan', 'yellow']
eventOfTheWeek = 0
issueNames = ['Immigration', 'Gun Control', 'Jobs', 'Tax Reform', 'Education']
stateOrganizations = {}
campaigningThisTurn = {}
adsThisTurn = {}
delegateCount = {}
stateSupport = {}

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

def setUpStates():                  #gets the positions of each state from the file in the folder.
    #stateNames = ['Alabama','Alaska','Arizona','Arkansas','California','Colorado','Connecticut','Delaware','Florida','Georgia','Hawaii','Idaho','Illinois','Indiana','Iowa','Kansas','Kentucky','Louisiana','Maine','Maryland','Massachusetts','Michigan','Minnesota','Mississippi','Missouri','Montana','Nebraska','Nevada','New Hampshire','New Jersey','New Mexico','New York','North Carolina','North Dakota','Ohio','Oklahoma','Oregon','Pennsylvania','Puerto Rico','Rhode Island','South Carolina','South Dakota','Tennessee','Texas','Utah','Vermont','Virginia','Washington','West Virginia','Wisconsin','Wyoming']
    states = open('statesPositions.txt', 'r')
    global statePositions
    for line in states:
        l = line.split(',')
        if l[0] != "State Name":
            statePositions[l[0]] = l[1:]
            stateOrganizations[l[0]] = []
            stateSupport[l[0]] = []

def setUpPlayers(numP, setUpWindow, mode):
    setUpWindow.destroy()
    global numPlayers
    global playerPositions
    global delegateCount
    numPlayers = numP
    for i in range(numPlayers):
        delegateCount[i+1] = 0
        playerPositions[i + 1] = []
        playerResources[i + 1] = [80, 100000]       #candidates time, money. Organization will be associated with each state
        for state in stateOrganizations:
            stateOrganizations[state].append(0)
            stateSupport[state].append(0)
    if mode == 1:
        for player in playerPositions:
            playerPositions[player] = [0,0,0,0,0]
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
    global playerPositions
    global numPlayers
    global player
    playerPositions[player] = [issue1, issue2, issue3, issue4, issue5]
    if player < numPlayers:
        player += 1
        setUpPlayer()
    else:
        player = 1
        calculateStateOpinions()
    
def paintNationalMap(event):         #his function will repaint the national map to show who is leading in each state
    global stateOpinions
    global playerColors

    natMapImage = Image.open('nationalMap.png')
    pixels = natMapImage.load()
    pixelList = open('pixelList.txt' , 'r')

    stateLeaders = {}
    for state in stateOpinions:
        try:
            opinions = stateOpinions[state]
            stateLeaders[state] = opinions.index(max(opinions)) + 1

        except KeyError:
            pass

    for line in pixelList:
        l = line.split(',')
        x = int(l[0])
        y = int(l[1])
        state = l[2].strip()
        try:
            leader = stateLeaders[state]
            color = playerColors[leader - 1]
            pixels[(x,y)] = 0
        except KeyError:
            pass
    natMapImage.show()

def createNationalMap():    #creates the main national map screen. This will be the main screen of the game, where the turn starts and ends.
    window = Tk()
    mapWindow = PanedWindow(window)

    global eventOfTheWeek
    global issueNames

    global player
    window.wm_title("Player " + str(player) + "\'s Turn")
    fundraising = 0

    natMapImage = Image.open("nationalMap.png")
    natMapImg = ImageTk.PhotoImage(natMapImage)

    menuBar = Menu(window)
    mainMenu = Menu(menuBar, tearoff = 0)
    mainMenu.add_command(label = "Save", command = saveGame)
    mainMenu.add_command(label = 'Load', command = loadGame)
    menuBar.add_cascade(label = 'Main Menu' , menu = mainMenu)
    window.config(menu = menuBar)

    calendarPane = PanedWindow(mapWindow, orient = VERTICAL)
    mapWindow.add(calendarPane)
    calendarTitle = Label(calendarPane, text = "Calendar of Primaries:", anchor = N, bg = 'blue')
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

    global playerResources
    resources = playerResources[player]
    moneyVar = StringVar()
    moneyVar.set('available money: %s' %(resources[1]))
    timeLabel = Label(resourcePane, text = "available candidate time: " + str(resources[0]), anchor = N)
    moneyLabel = Label(resourcePane, textvariable = moneyVar, anchor = N)

    global delegateCount
    for person in delegateCount:
        delegateLabel = Label(resourcePane, text = 'Player ' + str(person) + ' has ' + str(delegateCount[person]) + ' delegates')
        resourcePane.add(delegateLabel)

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
    global statePositions
    global stateOpinions
    stateName = '404'
    for line in pixelList:
        l = line.split(',')
        if xLoc == int(l[0]) and yLoc == int(l[1]):
            try:
                stateName = l[2].strip()
                stateWindow = Tk()
                stateWindow.wm_title(stateName)
                stats = statePositions[stateName]
                opinion = stateOpinions[stateName][player - 1]
                opinionLabel = Label(stateWindow, text = "Opinion of you: " + str(opinion))
                opinionLabel.pack()
                for i in range(len(stats)):
                    issue = Label(stateWindow, text = "Position on issue " + str(i) + ": " + str(stats[i]))
                    issue.pack()
                stateWindow.geometry('%dx%d+%d+%d' % (w, h, xLoc, yLoc))
                stateWindow.mainloop()
            except KeyError:
                tkMessageBox.showerror("state error","That's not a state")
                stateWindow.destroy()

def zoomToState(event):  #this will bring up the state window, seperate from the main window
    xLoc = event.x
    yLoc = event.y

    pixelList = open('pixelList.txt' , 'r')
    global statePositions
    global stateOpinions
    global issueNames
    global stateOrganizations
    global playerResources
    global campaigningThisTurn
    global player
    global stateSupport
    global numPlayers
    resources = playerResources[player]
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
                stats = statePositions[stateName]
                opinion = stateOpinions[stateName][player - 1]
                opinionLabel = Label(leftPane, text = "Opinion of you: " + str(opinion))
                leftPane.add(opinionLabel)

                for person in range(numPlayers):
                    supportLabel = Label(leftPane, text = 'Current Level of Support for Player ' + str(person+1) + ': ' + str(stateSupport[stateName][person]))
                    leftPane.add(supportLabel)

                districts = open('districts.txt' , 'r')
                delegates = 0
                for line in districts:
                    l = line.split(',')
                    if l[0].strip() == stateName:
                        delegates += int(l[2].strip())
                delegatesLabel = Label(leftPane, text = 'This State has ' + str(delegates) + " delegates")
                leftPane.add(delegatesLabel)

                eventOfTheWeekLabel = Label(leftPane, text = 'At the top of the news \n cycle this week: %s' %(issueNames[eventOfTheWeek]))
                leftPane.add(eventOfTheWeekLabel)
                for i in range(len(stats)):
                    issue = Label(leftPane, text = "Position on " + issueNames[i] + ": " + str(stats[i]), anchor = N)
                    leftPane.add(issue)
                statePane.add(leftPane)

                stateImage = Image.open(path + '\\stateDistricts\\' + stateName + '.jpeg')
                stateImg = ImageTk.PhotoImage(stateImage)

                stateImageLabel = Label(statePane, image = stateImg)
                statePane.add(stateImageLabel)

                currentOrg = stateOrganizations[stateName][player - 1]

                rightPane = PanedWindow(stateWindow, orient = VERTICAL)
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

                campaignSliderLabel = Label(rightPane, text = "How much time do you want\n to spend campainging here?")
                rightPane.add(campaignSliderLabel)
                campaignSlider = Scale(rightPane, orient = HORIZONTAL, from_ = 0, to = resources[0])
                allocatedTime = 0
                if stateName in campaigningThisTurn:
                    for candidate in campaigningThisTurn[stateName]:
                        if candidate[0] == player:
                            campaignSlider.set(candidate[1])
                            allocatedTime = candidate[1]
                rightPane.add(campaignSlider)

                districts = open("districts.txt", 'r')
                districtTitleLabel = Label(rightPane, text = "State Districts: ")
                rightPane.add(districtTitleLabel)
                addBuys = []
                for line in districts:
                    l = line.split(',')
                    if l[0] == stateName:
                        districtLabel = Label(rightPane, text = l[1].strip())
                        addBuySlider = Scale(rightPane, label = "Add buys for this district", from_ = 0, to = resources[1] / 3, resolution = 1000, orient = HORIZONTAL)
                        addBuys.append(addBuySlider)
                        rightPane.add(districtLabel)
                        rightPane.add(addBuySlider)

                doneButton = Button(rightPane, text = "Done with State", command = lambda : backToMap(event.widget.winfo_toplevel(), campaignSlider.get(), stateName, allocatedTime, addBuys), anchor = S)
                rightPane.add(doneButton)

                statePane.add(rightPane)
                statePane.pack()

                center(stateWindow)
                stateWindow.mainloop()
            except KeyError:
                tkMessageBox.showerror("state error","That's not a state")
                stateWindow.destroy()

def getOnBallot(player, stateName, cost, window, event):
    window.destroy()
    global stateOrganizations
    global playerResources
    global calendarOfContests
    global currentDate
    
    currentOrg = stateOrganizations[stateName][player - 1]
    for state in calendarOfContests:
        if stateName == state[0]:
            contestDate = state[1]

    if currentOrg == 0:
        if playerResources[player][1] - int(cost) >= 0 and currentDate < (contestDate - 1): 
            stateOrganizations[stateName][player - 1] = 1
            playerResources[player][1] = playerResources[player][1] - int(cost)
            zoomToState(event)
        elif playerResources[player][1] - int(cost) >= 0:
            tkMessageBox.showerror("Timing Error", "Too late to get on the Ballot here")
        elif currentDate < (contestDate - 1):
            tkMessageBox.showerror("Money Error", "You Don't have enough money to get on the ballot")
    else:
        if playerResources[player][1] - int(cost) >= 0: 
            stateOrganizations[stateName][player - 1] += 1
            playerResources[player][1] = playerResources[player][1] - int(cost)
            zoomToState(event)
        else:
            if currentOrg ==1:
                tkMessageBox.showerror("Money Error", "You Don't have enough money to build an office here")
            if currentOrg > 1:
                tkMessageBox.showerror("Money Error", "You Don't have enough money to further build your team here")

def backToMap(window, time, stateName, allocatedTime, addBuys):
    global playerResources
    global player
    global campaigningThisTurn
    global adsThisTurn

    totalAdCosts = 0
    for slider in addBuys:
        totalAdCosts += slider.get()

    if totalAdCosts > playerResources[player][1]:
        tkMessageBox.showerror("Money Error", "You don't have enough money for those ad buys")
    else:
        playerResources[player][1] -= totalAdCosts
        adTotal = 0
        for slider in addBuys:
            adTotal += slider.get()
        if stateName in adsThisTurn:
            adsThisTurn[stateName].append((player, adTotal))
        else:
            adsThisTurn[stateName] = [(player, adTotal)]

    if stateName in campaigningThisTurn:
        campaigningThisTurn[stateName].append((player, time))
    else:
        campaigningThisTurn[stateName] = [(player, time)]
    resources = playerResources[player]
    resources[0] -= time - allocatedTime
    window.destroy()
    createNationalMap()

def endTurn(window, fundraising):
    top = window.winfo_toplevel()
    top.destroy()
    global player
    global numPlayers
    global currentDate
    global eventOfTheWeek
    global campaigningThisTurn
    global delegateCount
    calcEndTurn(fundraising)

    if player < numPlayers:
        player += 1
    else: 
        currentDate += 1
        calculateStateOpinions()
        decideContests()
        player = 1
        eventOfTheWeek = random.randint(0,4)
        campaigningThisTurn = {}
        adsThisTurn = {}
    if currentDate <= 21:
        return
    else:
        winner = 0
        mostDelegates = 0
        for person in delegateCount:
            if delegateCount[person] > mostDelegates:
                winner = person
                mostDelegates = delegateCount[person]
        tkMessageBox.showinfo("Winner", "The Winner is: Player " + str(winner))
        exit()

def calcEndTurn(fundraising):      #this will calculate the new resources available to the player
    global player
    global playerResources
    global stateOpinions
    global stateOrganizations
    global stateSupport

    resources = playerResources[player]

    #time
    resources[0] = 80
    #money: remaining + fundraising + baseline + momentum + from states organization
    localFundraising = 0
    for state in stateOrganizations:
        localFundraising += stateOrganizations[state][player - 1] * 1000 + stateOrganizations[state][player - 1] * (stateSupport[state][player - 1]/2) * 1000 - stateOrganizations[state][player - 1] * 3000
    resources[1] = resources[1] + fundraising * 2000 + 20000 + localFundraising

def calculateStateOpinions():       #this function will calculate the opinion of each player in each state
    global statePositions
    global playerPositions
    global stateOpinions
    global currentDate
    global stateSupport
    global adsThisTurn
    global campaigningThisTurn

    if currentDate == 0:       #calculate the inital position of the opinions
        for state in statePositions:
            for player in playerPositions:
                opinion = 0
                for i in range(len(statePositions[state])):
                    opinion += int(statePositions[state][i].strip()) * playerPositions[player][i]     #the inital opinion is based on the differences on the issues between the state and the candidate.
                try:
                    stateOpinions[state].append(opinion)
                except KeyError:
                    stateOpinions[state] = [opinion]
        createNationalMap()

    else:               #each turn after that the new support is calculated. a player must be on the ballot (organization level 1) to get any support
        for state in stateSupport:
            orgs = stateOrganizations[state]

            if state in campaigningThisTurn:
                campaigning = campaigningThisTurn[state]
            else:
                campaigning = [[0,0]]
            if state in adsThisTurn:
                ads = adsThisTurn[state]
            else:
                ads = [[0,0]]

            for i in range(len(orgs)):
                person = i + 1
                org = orgs[i]
                for ad in ads:
                    if person == ad[0]:
                        adBuy = ad[1]
                    else:
                        adBuy = 0
                    for campaign in campaigning:
                        if person == campaign[0]:
                            campaignTime = campaign[1]
                        else:
                            campaignTime = 0
                        stateSupport[state][i] += campaignTime + org + (adBuy / 2000)
        print stateSupport["Iowa"]

def decideContests():
    global currentDate
    global calendarOfContests
    global stateSupport
    global stateOrganizations
    global numPlayers

    resultsWindow = Tk()
    a = 0
    for state in calendarOfContests:
        if state[1] + 1 == currentDate:
            a += 1
            stateName = state[0]
            support = stateSupport[stateName]
            orgs = stateOrganizations[stateName]
            winner = 0
            mostVotes = 0
            for i in range(numPlayers):
                if orgs[i] > 0:
                    votes = random.gauss(support[i], 30)
                    print votes
                    if votes > mostVotes:
                        winner = i + 1
                        mostVotes = votes
                else:
                    votes = 0
            if winner == 0:
                winner = random.randint(1, numPlayers)
            districts = open('districts.txt' , 'r')
            delegates = 0
            for line in districts:
                l = line.split(',')
                if l[0].strip() == stateName:
                    delegates += int(l[2].strip())
            delegateCount[winner] += delegates
            print stateName, winner, delegates
            resultsLabel = Label(resultsWindow, text = stateName + " is won by " + str(winner))
            resultsLabel.pack()
    if a >= 1:
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
    
    '''stateName = raw_input("what state")
    for point in endPoints:
        pixelList.write('%s,%s,%s \n' %(point[0], point[1], stateName))'''

main()