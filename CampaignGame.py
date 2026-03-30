#Campaign Game
#Drew Polasky
#support calculation is done in calculateStateOpinions
#money calculation is done in calcEndTurn

from __future__ import print_function
from tkinter import *
from PIL import Image, ImageTk
import os
import random
import time
import math
import sys
import pickle
import sys
from tkinter import messagebox
from tkinter import filedialog
from time import sleep

from State import State, District
from Player import Player
from tooltip import CreateToolTip

sys.setrecursionlimit(5000)

# Helper function for cross-platform mouse wheel support
def _bound_to_mousewheel(event, canvas):
    canvas.bind_all("<MouseWheel>", lambda e: _on_mousewheel(e, canvas))
    canvas.bind_all("<Button-4>", lambda e: _on_mousewheel(e, canvas))
    canvas.bind_all("<Button-5>", lambda e: _on_mousewheel(e, canvas))

def _unbound_to_mousewheel(event, canvas):
    canvas.unbind_all("<MouseWheel>")
    canvas.unbind_all("<Button-4>")
    canvas.unbind_all("<Button-5>")

def _on_mousewheel(event, canvas):
    # Handle both Windows (event.delta) and Mac/Linux (event.num)
    if hasattr(event, 'delta') and event.delta:
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    elif hasattr(event, 'num'):
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")

def _get_district_leader_color(district):
    """Return a muted background color based on who is leading in a district."""
    global playerColors
    if not district.pollingAverage or all(p == 0 for p in district.pollingAverage):
        return '#e8e8e8'  # neutral gray if no polling
    leader = district.pollingAverage.index(max(district.pollingAverage))
    # Create a very muted/pastel version of the player's color
    r, g, b = playerColors[leader]
    # Blend heavily toward white (80% white, 20% color)
    mr = int(r * 0.20 + 255 * 0.80)
    mg = int(g * 0.20 + 255 * 0.80)
    mb = int(b * 0.20 + 255 * 0.80)
    return '#%02x%02x%02x' % (mr, mg, mb)

#global variables for tracking players and turns
player = 1                  #keeps track of whose turn it is. indexed at 1
numTurns = 8
numPlayers = 2
currentDate = 1
players = {}            #dictionaries of class instances of players and states
states = {}
calendarOfContests = [('Iowa' , 4),('New Hampshire' , 5) ,('Nevada',7), ('South Carolina',8),('Minnesota',9),('Alabama' , 9), ('Arkansas', 9), ('Colorado', 9), ('Georgia', 9), ('Massachusetts', 9), ('North Dakota', 9), ('Oklahoma', 9), ('Tennessee', 9), ('Texas', 9), ('Vermont', 9), ('Virginia', 9), ('Kansas', 10), ('Kentucky', 10), ('Louisiana', 10), ('Maine', 10), ('Nebraska', 10), ('Hawaii', 10), ('Michigan', 10), ('Mississippi', 10), ('Wyoming', 11), ('Florida', 11), ('Illinois' , 11), ('Missouri', 11), ('North Carolina', 11), ('Ohio', 11), ('Arizona', 12), ('Idaho', 12), ('Utah', 12),('Alaska', 13), ('Washington', 13), ('Wisconsin', 14), ('New Jersey', 15), ('New York', 15), ('Connecticut', 15), ('Delaware', 15), ('Maryland', 15), ('Pennsylvania', 15), ('Rhode Island', 15), ('Indiana', 16), ('West Virginia', 16), ('Oregon', 17), ('California', 19), ('Montana', 19), ('New Mexico', 19), ('South Dakota', 19)]#, ('DC', 20)]
playerColors = [(255,0,0), (0,0,255), (0,255,0), (128,0,128)]
issueNames = ['Climate Change', 'Abortion','Taxes-Government Spending']#,'Immigration', 'Gun Control', 'Health Care', 'Tax Level', 'Regulation', 'Trade']
eventOfTheWeek = random.randint(0,len(issueNames)-1)
pastElections = {}          #stores the winner of each elections that's happened
weekResults = {}
issuesMode = False
issueLowRange = -1
issueHighRange = 1
randomPositions = False
issues_filename = 'issues.csv'
exit_status = False

def main():
    setUpStates()
    mainMenu()
    while True:
        if players[player].isHuman == 'human':
            showStartOfTurnReport()
            createNationalMap()
        else:
            calcAImove(players[player].isHuman)

def mainMenu():         #this will be the intial menu of the game, with options to start a new game, load a game, or run the tutorial
    mainMenuWindow = Tk()
    startGameButton = Button(mainMenuWindow, text = 'Start a New Game', command = lambda:setUpGame(mainMenuWindow))
    loadGameButton = Button(mainMenuWindow, text = 'Load Game', command = lambda:loadGame(mainMenuWindow))
    #tutorialButton = Button(mainMenuWindow, text = 'Launch the Tutorial', command = lambda:tutorial(mainMenuWindow))

    startGameButton.pack()
    loadGameButton.pack()
    #tutorialButton.pack()

    w = 400
    h = 300
    ws = mainMenuWindow.winfo_screenwidth() # width of the screen
    hs = mainMenuWindow.winfo_screenheight() # height of the screen
    # calculate x and y coordinates for the Tk root window
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)
    mainMenuWindow.geometry('%dx%d+%d+%d' % (w, h, x, y))

    mainMenuWindow.mainloop()

def tutorial(window):      
    window.destroy()

    tutorialWindow = Tk()

    welcomeLabel = Label(tutorialWindow, text = "Welcome to the Campaign! This tutorial will take you through the bascis of how the game is played, and get you ready to win the election" , wraplength = 400, justify = LEFT)
    introLabel = Label(tutorialWindow, text = "The goal of campaign is to win the election by amassing the most delegates. Delegates are won by winning state and district elections. State and district elections are won by having more people vote for you than your opponents. click the button below to get started, and see how you get people to vote for, rather than against you.", wraplength = 400, justify = LEFT)
    nextStepButton = Button(tutorialWindow, text = "Onwards", command = lambda:tutorialMap(tutorialWindow))

    w = 400
    h = 300
    ws = tutorialWindow.winfo_screenwidth() # width of the screen
    hs = tutorialWindow.winfo_screenheight() # height of the screen
    # calculate x and y coordinates for the Tk root window
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)
    tutorialWindow.geometry('%dx%d+%d+%d' % (w, h, x, y))

    welcomeLabel.pack()
    introLabel.pack()
    nextStepButton.pack()

    tutorialWindow.mainloop()

def tutorialMap(window):            #my idea is to have an annotated map, first of the national map, then of the state map for any new players to look at to get an idea of what is going on and what everything does. I think I should be able to have the national map fixed and have text boxes pop up and disappear explaining each piece.
    window.destroy()
    tutorialMapWindow = Tk()
    natMapImage = Image.open("tutorialNationalMap.jpg")
    natMapImg = ImageTk.PhotoImage(natMapImage)
    natMap = Label(tutorialMapWindow, image = natMapImg)
    natMap.pack()
    center(tutorialMapWindow)

    message = Tk()         #this message will explain the colors on the map, and will have a button for the player to advance through the tutorial
    messageLabel = Label(message, text = "This is the national map for the campaign, where you will start and end each turn. There is a great deal of information on this screen, so we'll start with the map itself. Each state is colored based on who is currently leading in the polls in that state or, if the state has already voted, who won. The states that have already voted are colored in a darker shade of the players color than those that have yet to vote. At the top of the right side bar you can see which color correspond to each player. In this example, player 1 (red) has already won in a number of states including Texas and Michigan, and is leading in California, Arizona, and Utah. States in white are places where no candidate has any support. At the top of the screen, the main menu has options to save or load a game. Took look at a state in more detail, and to make desicions about what resources you want to spend there, you'll click on the state you want to zoom to.", wraplength = 400, justify = LEFT)
    nextStepButton = Button(message, text = "Onwards", command = lambda:tutorialMapSecondMessage(message, tutorialMapWindow))
    messageLabel.pack()
    nextStepButton.pack()

    for i in range(2):
        if i == 1:
            message.mainloop()
        tutorialMapWindow.update_idletasks()

def tutorialMapSecondMessage(message, mapWindow):
    message.destroy()
    message = Tk()         #this message will explain the colors on the map, and will have a button for the player to advance through the tutorial
    messageLabel = Label(message, text = 'If you look now to the left of the screen, you will see the campaign calendar. At the top you can see what week it is right now (in this case, its week 11). Below that you can see the upcoming elections. Elections take place at the end of the turn, so Wyoming, Florida, and the other states that vote on week eleven will hold their elections after the last player ends their turn this week. Timing your campaining in states is important, in the two weeks before the election, your campaining will be more effective, as people start to pay more attention to politics.', wraplength = 400, justify = LEFT)
    nextStepButton = Button(message, text = "Onwards", command = lambda:tutorialMapThirdMessage(message, mapWindow))
    messageLabel.pack()
    nextStepButton.pack()

def tutorialMapThirdMessage(message, mapWindow):
    message.destroy()
    message = Tk()         #this message will explain the colors on the map, and will have a button for the player to advance through the tutorial
    messageLabel = Label(message, text = 'Finally on this screen we have the right side bar, which has a variety of information about your campaign. First, at the top, we have how many delegates each player has won to this point.\n Just below that is your current momentum score. Momentum is gotten by winning states and district, but there is a fixed amount for each turn, so winning Iowa, which is the only contest on week 4, gives a lot more momentum than winning Minnesota, one of many contests on week 9(super tuesday). Momentum makes people more likely to vote for you and donate to your campaign, but it fades quickly if you stop winning.\n Below momentum are your available resoures, time and money. Time is your candidates time, and can either be spent campaigning directly in a state to build support, or fundraising, soliciting big donations to increase the war chest. Money can be spent to build your ground game in states, or to buy advertising to increase support. We\'ll go into more depth on those options when we get to the state screen later on.\n Under your resources is the issue of the week. If you are playing without issues, you can ignore this.\n Next comes the fundraising slider, which lets you choose how much of your candidates time you want to spend raising money, and finally we have the end turn button, which ends your turn. With that, let\'s take a look at the state map.', wraplength = 400, justify = LEFT)
    nextStepButton = Button(message, text = "Onwards", command = lambda:tutorialState(message, mapWindow))
    messageLabel.pack()
    nextStepButton.pack()

def tutorialState(window, mapWindow):           #now do the tutorial explaining the state maps in the same way
    window.destroy()
    mapWindow.destroy()

    tutorialMapWindow = Tk()
    natMapImage = Image.open("tutorialStateMap.jpg")
    natMapImg = ImageTk.PhotoImage(natMapImage)
    natMap = Label(tutorialMapWindow, image = natMapImg)
    natMap.pack()
    center(tutorialMapWindow)

    message = Tk()         #this message will explain the colors on the map, and will have a button for the player to advance through the tutorial
    messageLabel = Label(message, text = "", wraplength = 400, justify = LEFT)
    nextStepButton = Button(message, text = "Onwards", command = lambda:tutorialMapSecondMessage(message, tutorialMapWindow))
    messageLabel.pack()
    nextStepButton.pack()

    for i in range(2):
        if i == 1:
            message.mainloop()
        tutorialMapWindow.update_idletasks()

def setUpGame(window):        #this will set up the basic parameters of the game, or have the option to load a previously saved game.  
    window.destroy()
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

    turnChoices = [8,10,20]
    numTurnsVar = IntVar(value=turnChoices[0])
    turnsLabel = Label(setUpWindow, text = 'Number of Turns')
    gameLength = OptionMenu(setUpWindow, numTurnsVar, *turnChoices)

    startGame = Button(setUpWindow, text = 'Start Game', command = lambda:setUpPlayers(numP.get(), setUpWindow, mode.get(), numTurnsVar.get()))
    numP = Scale(setUpWindow, label = 'Number of Players', orient = HORIZONTAL, from_= 2, to_ = 10)

    numP.pack()
    turnsLabel.pack()
    gameLength.pack()
    startGame.pack()
    setUpWindow.mainloop()

def setCalendar(numTurns):
    global calendarOfContests
    print(numTurns)
    if numTurns == 20:
        # Use the default full calendar already defined globally
        calendarOfContests = [('Iowa' , 4),('New Hampshire' , 5) ,('Nevada',7), ('South Carolina',8),('Minnesota',9),('Alabama' , 9), ('Arkansas', 9), ('Colorado', 9), ('Georgia', 9), ('Massachusetts', 9), ('North Dakota', 9), ('Oklahoma', 9), ('Tennessee', 9), ('Texas', 9), ('Vermont', 9), ('Virginia', 9), ('Kansas', 10), ('Kentucky', 10), ('Louisiana', 10), ('Maine', 10), ('Nebraska', 10), ('Hawaii', 10), ('Michigan', 10), ('Mississippi', 10), ('Wyoming', 11), ('Florida', 11), ('Illinois' , 11), ('Missouri', 11), ('North Carolina', 11), ('Ohio', 11), ('Arizona', 12), ('Idaho', 12), ('Utah', 12),('Alaska', 13), ('Washington', 13), ('Wisconsin', 14), ('New Jersey', 15), ('New York', 15), ('Connecticut', 15), ('Delaware', 15), ('Maryland', 15), ('Pennsylvania', 15), ('Rhode Island', 15), ('Indiana', 16), ('West Virginia', 16), ('Oregon', 17), ('California', 19), ('Montana', 19), ('New Mexico', 19), ('South Dakota', 19)]
        return
    calendarOfContests = []
    if numTurns == 10:
        calendarFile = open('shortSchedule.txt' ,'r')
    elif numTurns == 8:
        calendarFile = open('8weekSchedule.txt' ,'r')
    for line in calendarFile:
        line = line.split(',')
        calendarOfContests.append((line[0],int(line[1])))

def setUpStates(): 
    statesList = open('statesPositions.txt', 'r')
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

def setUpPlayers(numP, setUpWindow, mode, numTurn_menu):
    setUpWindow.destroy()
    global numPlayers
    global issuesMode
    global numTurns
    numTurns = numTurn_menu

    setCalendar(numTurns)

    if mode == 2:
        issuesMode = True

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
        states[state].updateSupport(numPlayers, calendarOfContests, currentDate)

    #if mode == 1:       #mode 1 is no issues mode, set the players views to 0 for all issues
    #    for person in players:
    #        players[person].setPositions([0,0,0,0,0])
    #    calculateStateOpinions()
    else:
        setUpPlayer(mode)

def setUpPlayer(mode):      #this function will create the screen to set up a candidate initially. 
    setUpPlayerWindow = Tk()
    setUpPlayerWindow.wm_title("Choose Positions for player " + str(player))
    w = 400 # width for the Tk root
    h = 600 # height for the Tk root

    # get screen width and height
    ws = setUpPlayerWindow.winfo_screenwidth() # width of the screen
    hs = setUpPlayerWindow.winfo_screenheight() # height of the screen

    # calculate x and y coordinates for the Tk root window
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)

    # set the dimensions of the screen 
    # and where it is placed
    setUpPlayerWindow.geometry('%dx%d+%d+%d' % (w, h, x, y))

    nameLabel = Label(setUpPlayerWindow, text = 'Your Name: ')
    nameLabel.pack()
    name = Entry(setUpPlayerWindow)
    name.pack()

    default = StringVar(setUpPlayerWindow)
    default.set('human')
    isHuman = OptionMenu(setUpPlayerWindow, default, 'human','AI')
    isHuman.pack()

    issueSliders = []
    for issue in issueNames:
        issueSliders.append(Scale(setUpPlayerWindow, from_ = issueLowRange, to_ = issueHighRange, label = issue, orient = HORIZONTAL, length = 300))

    if mode == 2:
        for issueSlider in issueSliders:
            issueSlider.pack()

    endChoose = Button(setUpPlayerWindow, text = 'Done With Setup', command = lambda: setPositions(list(map(lambda x:x.get(),issueSliders)), name.get(), default.get(), setUpPlayerWindow, mode))
    endChoose.pack()
    setUpPlayerWindow.mainloop()

def setPositions(issues, name, isHuman, setUpPlayerWindow, mode):
    setUpPlayerWindow.destroy()
    global player
    person = players[player]
    person.setPositions(issues)
    person.setHuman(isHuman)
    person.setName(name)
    if player < numPlayers:
        player += 1
        setUpPlayer(mode)
    else:
        player = 1
        if issuesMode: #set the district level positions on the issues, if issues mode is on, otherwise all netural
            if randomPositions:
                for state in states:
                    for district in states[state].districts:
                        district.setPositions([random.randint(issueLowRange, issueHighRange) for i in range(len(issueNames))])
            else:
                issuesFile = open(issues_filename, 'r')
                header = issuesFile.readline()
                header = [x.strip() for x in header.split(',')]
                positionLocations = [header.index(issue) for issue in issueNames]
                for line in issuesFile.readlines():
                    try:
                        line = [x.strip() for x in line.split(',')]
                        state = states[line[0]]
                        for district in state.districts:
                            if district.name == line[1]:
                                positions = [float(line[i]) for i in positionLocations]
                                district.setPositions(positions)
                    except KeyError:
                        pass
        else:
            for state in states:
                 for district in states[state].districts:
                    district.setPositions([0 for i in range(len(issueNames))])

        calculateStateOpinions()
    
def showStartOfTurnReport():
    global currentDate
    global player
    global players

    if currentDate > 1 and players[player].isHuman == 'human':
        reportWindow = Tk()
        #reportWindow = PanedWindow(report, orient = VERTICAL)

        #at the top, the week that it is
        title = Label(reportWindow, text = 'Start of turn report for week ' + str(currentDate), anchor = N)
        #reportWindow.add(title)

        #next, income from both direct fundrasing and small donations
        fundraisingIncome = players[player].history[currentDate - 1]['fundraisingIncome']
        localIncome = players[player].history[currentDate - 1]['localIncome']
        income = Label(reportWindow, text = 'Total income: ' +str(fundraisingIncome + localIncome), anchor = N).grid(row=0, columnspan = 4)
        incomeParts = Label(reportWindow, text = 'Fundraising Income: ' + str(fundraisingIncome) + ', Local Fundraising Income: ' + str(localIncome)).grid(row=1, columnspan = 4)
        #reportWindow.add(income)
        #reportWindow.add(incomeParts)

        #report the results for the previous week
        resultsLabel = Label(reportWindow, text = 'Results: ').grid(row=2, columnspan = 4)
        labelrow = 3
        playerLabel = Label(reportWindow, text = 'Player').grid(row=labelrow, column =0)
        delegateLabel = Label(reportWindow, text = 'Delegates Won').grid(row = labelrow, column=1)
        statesLabel = Label(reportWindow, text = 'States Won').grid(row = labelrow, column = 2)
        districtsLabel = Label(reportWindow, text = 'Districts Won').grid(row=labelrow, column = 3)
        labelrow += 1
        for person in weekResults:
            Label(reportWindow, text = players[person].publicName).grid(row=labelrow, column = 0, rowspan = 2)
            j = 1
            for resultType in weekResults[person].keys():
                if type(weekResults[person][resultType]) == int or type(weekResults[person][resultType]) == float:
                    resultsList = [str(weekResults[person][resultType])]
                else:
                    resultsList = weekResults[person][resultType]
                Label(reportWindow, text=' '.join(resultsList), wraplength=500).grid(row=labelrow, column = j, rowspan = 2)
                j += 1
            labelrow += 2

        doneButton = Button(reportWindow, text = 'Done', command = lambda : startTurn(reportWindow)).grid(row = labelrow+1, columnspan = 4)


        #reportWindow.pack()
        center(reportWindow)
        reportWindow.mainloop()
        return
    else:
        return

def startTurn(window):
    window.destroy()
    return

def _muted_map_color(color, saturation=0.75):
    """Blend a player color toward white to produce a muted map color.
    saturation=1.0 is full color, 0.0 is pure white."""
    r = int(color[0] * saturation + 255 * (1 - saturation))
    g = int(color[1] * saturation + 255 * (1 - saturation))
    b = int(color[2] * saturation + 255 * (1 - saturation))
    return (r, g, b)

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
                    stateLeaders[state] = [pastElections[state] - 1, 0.8]
                elif stateTime[0] == state:
                    support = states[state].pollingAverage
                    if max(support) > 0:
                        stateLeaders[state] = [support.index(max(support)), 1]
        except KeyError:
            pass
    for line in pixelList:
        l = line.split(',')
        x = int(l[0])
        y = int(l[1])
        state = l[2].strip()
        try:
            leader = stateLeaders[state][0]
            color = playerColors[leader]
            factor = stateLeaders[state][1]  # 0.8 for past elections, 1.0 for leading
            # Past elections: more saturated (0.70); leading future states: lighter (0.50)
            saturation = 0.70 if factor < 1.0 else 0.50
            newColor = _muted_map_color(color, saturation)
            pixels[(x,y)] = newColor
        except KeyError:
            pass
    return natMapImage

def paintStateMap(stateMapImage, stateName):
    global states
    global playerColors
    global calendarOfContests
    global currentDate
    global pastElections

    pixels = stateMapImage.load()
    cwd = os.getcwd()
    try:
        pixelList = open(cwd + '\\stateDistricts\\' + stateName + '.txt', 'r')
    except IOError:
        pixelList = open(cwd + '/stateDistricts/' + stateName + '.txt', 'r')

    districtLeaders = {}
    try: 
        for district in states[stateName].districts:
            support = district.support
            if max(support) > 0:
                districtLeaders[district.name] = support.index(max(support))
            print(district.name, support.index(max(support)), support)
    except KeyError:
        pass
    for line in pixelList:
        l = line.split(',')
        state = l[2].strip()
        if state == stateName:
            x = int(l[0])
            y = int(l[1])
            districtName = l[3].strip()
            try:
                leader = districtLeaders[districtName]
                color = playerColors[leader]
                pixels[(x,y)] = _muted_map_color(color, 0.50)
            except:
                pass
    return stateMapImage

def createNationalMap():    #creates the main national map screen. This will be the main screen of the game, where the turn starts and ends.
    window = Tk()
    mapWindow = PanedWindow(window)
    global eventOfTheWeek
    global issueNames
    global currentDate
    global player
    global players
    window.wm_title(players[player].publicName + "\'s Turn")
    fundraising = 0

    natMapImage = Image.open("nationalMap.jpg")
    natMapImage = paintNationalMap(natMapImage)
    natMapImg = ImageTk.PhotoImage(natMapImage)

    menuBar = Menu(window)
    mainMenu = Menu(menuBar, tearoff = 0)
    mainMenu.add_command(label = "Save", command = saveGame)
    mainMenu.add_command(label = 'Load', command = lambda : loadGame(window))
    menuBar.add_cascade(label = 'Main Menu' , menu = mainMenu)
    window.config(menu = menuBar)

    # Create scrollable calendar panel
    calendarFrame = Frame(mapWindow, width=250)
    calendarCanvas = Canvas(calendarFrame, width=250, highlightthickness=0)
    calendarScrollbar = Scrollbar(calendarFrame, orient="vertical", command=calendarCanvas.yview)
    calendarScrollableFrame = Frame(calendarCanvas)
    
    calendarScrollableFrame.bind(
        "<Configure>",
        lambda e: calendarCanvas.configure(scrollregion=calendarCanvas.bbox("all"))
    )
    
    calendarCanvas.create_window((0, 0), window=calendarScrollableFrame, anchor="nw")
    calendarCanvas.configure(yscrollcommand=calendarScrollbar.set)
    
    calendarCanvas.pack(side="left", fill="both", expand=True)
    calendarScrollbar.pack(side="right", fill="y")
    
    mapWindow.add(calendarFrame)
    
    calendarTitle = Label(calendarScrollableFrame, text = "Calendar of Primaries:", anchor = N)
    current = Label(calendarScrollableFrame, text = 'Week of the campaign number ' + str(currentDate), anchor = N)
    
    calendarTitle.pack(anchor="n", fill="x")
    current.pack(anchor="n", fill="x")
    
    # Add mouse wheel support for calendar panel
    calendarCanvas.bind("<Enter>", lambda e: _bound_to_mousewheel(e, calendarCanvas))
    calendarCanvas.bind("<Leave>", lambda e: _unbound_to_mousewheel(e, calendarCanvas))

    k = 0
    j=0
    while j < len(calendarOfContests):     #display all contests in the scrollable left bar
        nextContest = calendarOfContests[j]
        name = nextContest[0]
        date = nextContest[1]
        if date < currentDate:
            # Past contests shown grayed out
            nextContestLabel = Label(calendarScrollableFrame, text = name + " - week " + str(date), fg='#999999')
        else:
            nextContestLabel = Label(calendarScrollableFrame, text = name + " - week " + str(date))
        nextContestLabel.pack(anchor="n", fill="x")
        j+=1
    placeHolderLabel4 = Label(calendarScrollableFrame, anchor = N)
    placeHolderLabel4.pack(anchor="n", fill="x")

    natMap = Label(mapWindow, image = natMapImg)
    mapWindow.add(natMap)   

    # Create scrollable resource panel
    resourceFrame = Frame(mapWindow, width=300)
    resourceCanvas = Canvas(resourceFrame, width=300, highlightthickness=0)
    resourceScrollbar = Scrollbar(resourceFrame, orient="vertical", command=resourceCanvas.yview)
    resourceScrollableFrame = Frame(resourceCanvas)
    
    resourceScrollableFrame.bind(
        "<Configure>",
        lambda e: resourceCanvas.configure(scrollregion=resourceCanvas.bbox("all"))
    )
    
    resourceCanvas.create_window((0, 0), window=resourceScrollableFrame, anchor="nw")
    resourceCanvas.configure(yscrollcommand=resourceScrollbar.set)
    
    resourceCanvas.pack(side="left", fill="both", expand=True)
    resourceScrollbar.pack(side="right", fill="y")
    
    mapWindow.add(resourceFrame)
    
    # Add mouse wheel support for resource panel
    resourceCanvas.bind("<Enter>", lambda e: _bound_to_mousewheel(e, resourceCanvas))
    resourceCanvas.bind("<Leave>", lambda e: _unbound_to_mousewheel(e, resourceCanvas))

    resources = players[player].resources
    moneyVar = StringVar()
    moneyVar.set('available money: %s' %(resources[1]))
    timeLabel = Label(resourceScrollableFrame, text = "available candidate time: " + str(resources[0]), anchor = N)
    moneyLabel = Label(resourceScrollableFrame, textvariable = moneyVar, anchor = N)
    
    timeLabel.pack(anchor="n", fill="x")
    moneyLabel.pack(anchor="n", fill="x")

    global playerColors
    for person in players:
        color = _muted_map_color(playerColors[person - 1], 0.70)
        color = '#%02x%02x%02x' % color
        delegateLabel = Label(resourceScrollableFrame, text = str(players[person].publicName) + ' has ' + str(players[person].delegateCount) + ' delegates', bg = color)
        delegateLabel.pack(anchor="n", fill="x")
        issueStrings = []
        for issue in range(len(issueNames)):
            issueStrings.append(issueNames[issue] + ' ' + str(players[person].positions[issue]))
        player_ttp = CreateToolTip(delegateLabel, ('\n').join(issueStrings))

    momentumLabel = Label(resourceScrollableFrame, text = 'Your Current Momentum is: ' + str(round(players[player].momentum, 0)))
    momentumLabel.pack(anchor="n", fill="x")

    placeHolderLabel3 = Label(resourceScrollableFrame, anchor = S)
    placeHolderLabel3.pack(anchor="n", fill="x")

    eventOfTheWeekLabel = Label(resourceScrollableFrame, text = 'At the top of the news \n cycle this week: %s' %(issueNames[eventOfTheWeek]))
    eventOfTheWeekLabel.pack(anchor="n", fill="x")

    placeHolderLabel = Label(resourceScrollableFrame, anchor = S)  
    placeHolderLabel.pack(anchor="n", fill="x")
    placeHolderLabel2 = Label(resourceScrollableFrame, anchor = S)
    placeHolderLabel2.pack(anchor="n", fill="x")

    fundraisingLabel = Label(resourceScrollableFrame, text = 'How much time do you want \n to spend fundraising this week?')
    fundraisingLabel.pack(anchor="n", fill="x")
    fundraisingScale = Scale(resourceScrollableFrame, orient = HORIZONTAL, from_ = 0, to = resources[0], variable = fundraising)
    fundraisingScale.pack(anchor="n", fill="x")
    
    endTurnButton = Button(resourceScrollableFrame, text = 'End Turn', command = lambda : endTurn(window, fundraisingScale.get()), anchor = S)
    endTurnButton.pack(anchor="n", fill="x")

    natMap.image = natMapImage
    mapWindow.pack()
    #natMap.bind('<Enter>', showStats)

    center(window)
    natMap.bind('<Button-1>', zoomToState)
    window.protocol("WM_DELETE_WINDOW", exitGame)
    window.mainloop()
        
def center(toplevel):          
    toplevel.update_idletasks()  #copied from an answer by user Wayne Werner on stackoverflow
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
                messagebox.showerror("state error","That's not a state")

def zoomToState(event):  #this will bring up the state window, seperate from the main window
    xLoc = event.x
    yLoc = event.y - 20

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
                
                # Create scrollable left panel
                leftPanelWidth = 400
                leftFrame = Frame(statePane, width=leftPanelWidth)
                leftCanvas = Canvas(leftFrame, width=leftPanelWidth, highlightthickness=0)
                leftScrollbar = Scrollbar(leftFrame, orient="vertical", command=leftCanvas.yview)
                leftScrollableFrame = Frame(leftCanvas, width=leftPanelWidth)
                
                leftScrollableFrame.bind(
                    "<Configure>",
                    lambda e: leftCanvas.configure(scrollregion=leftCanvas.bbox("all"))
                )
                
                leftCanvas.create_window((0, 0), window=leftScrollableFrame, anchor="nw")
                leftCanvas.configure(yscrollcommand=leftScrollbar.set)
                
                leftCanvas.pack(side="left", fill="both", expand=True)
                leftScrollbar.pack(side="right", fill="y")
                
                statePane.add(leftFrame)
                
                # Add mouse wheel support for left panel
                leftCanvas.bind("<Enter>", lambda e: _bound_to_mousewheel(e, leftCanvas))
                leftCanvas.bind("<Leave>", lambda e: _unbound_to_mousewheel(e, leftCanvas))
                
                stateWindow.wm_title(stateName)
                stats = states[stateName].positions
                #opinion = states[stateName].opinions[player - 1]
                #opinionLabel = Label(leftScrollableFrame, text = "Opinion of you: " + str(opinion))
                #opinionLabel.pack(anchor="n", fill="x")

                for person in range(numPlayers):
                    supportLabel = Label(leftScrollableFrame, text = 'Current Polling for ' + players[person+1].publicName + ': ' + str(states[stateName].pollingAverage[person]), wraplength=leftPanelWidth-20, justify=LEFT)
                    supportLabel.pack(anchor="n", fill="x")

                districts = open('districts.txt' , 'r')
                delegates = 0
                for line in districts:
                    l = line.split(',')
                    if l[0].strip() == stateName:
                        delegates += int(l[2].strip()) * 3
                delegatesLabel = Label(leftScrollableFrame, text = 'This State has ' + str(delegates) + " delegates")
                delegatesLabel.pack(anchor="n", fill="x")

                for di, district in enumerate(states[stateName].districts):
                    dBg = _get_district_leader_color(district)
                    # Separator line between districts
                    sep = Frame(leftScrollableFrame, height=2, bd=1, relief=SUNKEN)
                    sep.pack(fill="x", padx=5, pady=4)
                    districtDelegatesLabel = Label(leftScrollableFrame, text = district.name + " District - " + str(int(district.population)) + " delegates", bg=dBg, font=('TkDefaultFont', 9, 'bold'), wraplength=leftPanelWidth-20, justify=LEFT)

                    issueStrings = []
                    for issue in range(len(issueNames)):
                        issueStrings.append(issueNames[issue] + ' ' + str(district.positions[issue]))
                    delegatesLabel_ttp = CreateToolTip(districtDelegatesLabel, '\n'.join(issueStrings) )

                    districtDelegatesLabel.pack(anchor="n", fill="x")
                    for person in range(numPlayers):
                        districtSupportLabel = Label(leftScrollableFrame, text = players[person+1].publicName + ': ' + str(district.pollingAverage[person]) + '%', bg=dBg, wraplength=leftPanelWidth-20, justify=LEFT)
                        districtSupportLabel.pack(anchor="n", fill="x")

                '''eventOfTheWeekLabel = Label(leftScrollableFrame, text = 'At the top of the news \n cycle this week: %s' %(issueNames[eventOfTheWeek]))
                eventOfTheWeekLabel.pack(anchor="n", fill="x")
                for i in range(len(stats)):
                    issue = Label(leftScrollableFrame, text = "Position on " + issueNames[i] + ": " + str(stats[i]), anchor = N)
                    issue.pack(anchor="n", fill="x")'''
                placeHolderLabel = Label(leftScrollableFrame)
                placeHolderLabel.pack(anchor="n", fill="x")
                try:
                    stateImage = Image.open(path + '\\stateDistricts\\' + stateName + '.jpeg')
                except IOError:        #for linux/mac paths
                    stateImage = Image.open(path + '/stateDistricts/' + stateName + '.jpeg')
                stateImage = paintStateMap(stateImage, stateName)
                stateImg = ImageTk.PhotoImage(stateImage)

                stateImageLabel = Label(statePane, image = stateImg)
                statePane.add(stateImageLabel)

                currentOrg = states[stateName].organizations[player-1]

                # Create scrollable right panel
                rightFrame = Frame(stateWindow, width=350)
                rightCanvas = Canvas(rightFrame, width=350, highlightthickness=0)
                rightScrollbar = Scrollbar(rightFrame, orient="vertical", command=rightCanvas.yview)
                rightScrollableFrame = Frame(rightCanvas)
                
                rightScrollableFrame.bind(
                    "<Configure>",
                    lambda e: rightCanvas.configure(scrollregion=rightCanvas.bbox("all"))
                )
                
                rightCanvas.create_window((0, 0), window=rightScrollableFrame, anchor="nw")
                rightCanvas.configure(yscrollcommand=rightScrollbar.set)
                
                rightCanvas.pack(side="left", fill="both", expand=True)
                rightScrollbar.pack(side="right", fill="y")
                
                statePane.add(rightFrame)
                
                # Add mouse wheel support for right panel
                rightCanvas.bind("<Enter>", lambda e: _bound_to_mousewheel(e, rightCanvas))
                rightCanvas.bind("<Leave>", lambda e: _unbound_to_mousewheel(e, rightCanvas))
                
                if currentOrg == 0:      #if the player has not yet on the ballot in the state
                    ballotLabel = Label(rightScrollableFrame, text = 'Cost to get on the ballot ' + stateName + ': $10,000')
                    ballotButton = Button(rightScrollableFrame, text = 'Get on the Ballot', command = lambda : getOnBallot(player, stateName, 10000, stateWindow, event))
                    ballotLabel.pack(anchor="n", fill="x")
                    ballotButton.pack(anchor="n", fill="x")

                if currentOrg == 1: #to establish a field office in the state
                    establishLabel = Label(rightScrollableFrame, text = 'Cost to establish a field office in ' + stateName + ': $10,000')
                    establishButton = Button(rightScrollableFrame, text = 'Build field office', command = lambda : getOnBallot(player, stateName, 10000, stateWindow, event))
                    establishLabel.pack(anchor="n", fill="x")
                    establishButton.pack(anchor="n", fill="x")

                if currentOrg > 1:
                    buildLabel = Label(rightScrollableFrame, text = 'Cost to further develop your organization in ' + stateName + ':' + str(10000 * currentOrg))
                    buildButton = Button(rightScrollableFrame, text = 'Build More Organization', command = lambda : getOnBallot(player, stateName, 10000 * currentOrg, stateWindow, event))
                    buildLabel.pack(anchor="n", fill="x")
                    buildButton.pack(anchor="n", fill="x")
                orgLabel = Label(rightScrollableFrame, text = 'Your current organization level in this state: ' + str(currentOrg), anchor = N)
                orgLabel.pack(anchor="n", fill="x")

                districts = open("districts.txt", 'r')
                districtTitleLabel = Label(rightScrollableFrame, text = "State Districts: ")
                districtTitleLabel.pack(anchor="n", fill="x")
                addBuys = []
                campaingingTime = []
                allocatedTime = 0
                allocatedMoney = 0
                j = 0
                for line in districts:
                    l = line.split(',')
                    if l[0] == stateName:
                        dBg = _get_district_leader_color(states[stateName].districts[j])
                        # Separator line between districts
                        sep = Frame(rightScrollableFrame, height=2, bd=1, relief=SUNKEN)
                        sep.pack(fill="x", padx=5, pady=4)
                        districtLabel = Label(rightScrollableFrame, text = l[1].strip(), bg=dBg, font=('TkDefaultFont', 9, 'bold'))
                        districtAllocatedTime = states[stateName].districts[j].campaigningThisTurn[player - 1]
                        districtAllocatedMoney = states[stateName].districts[j].adsThisTurn[player - 1]
                        addBuySlider = Scale(rightScrollableFrame, label = "Ad buys", from_ = 0, to = resources[1] + districtAllocatedMoney, resolution = 1000, orient = HORIZONTAL, bg=dBg)
                        campaigningSlider = Scale(rightScrollableFrame, label = "Campaigning time", from_ = 0, to = resources[0] + districtAllocatedTime, orient = HORIZONTAL, bg=dBg)
                        
                        campaigningSlider.set(districtAllocatedTime)
                        allocatedTime += districtAllocatedTime
                        
                        addBuySlider.set(districtAllocatedMoney)
                        allocatedMoney += districtAllocatedMoney

                        j += 1
                        addBuys.append(addBuySlider)
                        campaingingTime.append(campaigningSlider)
                        districtLabel.pack(anchor="n", fill="x")
                        campaigningSlider.pack(anchor="n", fill="x")
                        addBuySlider.pack(anchor="n", fill="x")

                doneButton = Button(rightScrollableFrame, text = "Done with State", command = lambda : backToMap(event.widget.winfo_toplevel(), campaingingTime, stateName, allocatedTime, allocatedMoney, addBuys), anchor = S)
                doneButton.pack(anchor="n", fill="x")

                statePane.pack()

                center(stateWindow)
                stateWindow.mainloop()
            except KeyError:
                messagebox.showerror("state error","That's not a state")
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
        if players[player].resources[1] - int(cost) >= 0:# and currentDate < (contestDate - 1): 
            states[stateName].organizations[player-1] = 1
            players[player].resources[1] = players[player].resources[1] - int(cost)
            zoomToState(event)
        elif players[player].resources[1] - int(cost) >= 0:
            messagebox.showerror("Timing Error", "Too late to get on the Ballot here")
        elif currentDate < (contestDate - 1):
            messagebox.showerror("Money Error", "You Don't have enough money to get on the ballot")
    else:
        if players[player].resources[1] - int(cost) >= 0: 
            states[stateName].organizations[player-1] += 1
            players[player].resources[1] = players[player].resources[1] - int(cost)
            zoomToState(event)
        else:
            if currentOrg ==1:
                messagebox.showerror("Money Error", "You Don't have enough money to build an office here")
            if currentOrg > 1:
                messagebox.showerror("Money Error", "You Don't have enough money to further build your team here")

def backToMap(window, campaingingTime, stateName, allocatedTime, allocatedMoney, addBuys):
    global player
    global states
    global players

    totalAdCosts = 0
    totalTime = 0
    players[player].resources[1] += allocatedMoney
    players[player].resources[0] += allocatedTime
    for slider in addBuys:
        totalAdCosts += slider.get()
    for slider in campaingingTime:
        totalTime += slider.get()

    if totalAdCosts > players[player].resources[1]:
        messagebox.showerror("Money Error", "You don't have enough money for those ad buys")
        players[player].resources[1] -= allocatedMoney
        players[player].resources[0] -= allocatedTime
    elif totalTime > players[player].resources[0]:
        messagebox.showerror("Time Error", "You don't have enough time for all that campaigning")
        players[player].resources[1] -= allocatedMoney
        players[player].resources[0] -= allocatedTime
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
    global numTurns

    #print('hours of fundraising: ', fundraising)
    players[player].resources[0] -= fundraising     #this and the next line could be combined, but in case I come back later and change things, this should be more clear
    fundraising += players[player].resources[0]     #add any left over hours to the fundraising time
    #print('hours of fundraising: ', fundraising)
    calcEndTurn(fundraising)

    if player < numPlayers:
        player += 1
    else: 
        calculateStateOpinions()
        currentDate += 1
        decideContests()
        player = 1
        eventOfTheWeek = random.randint(0,len(issueNames)-1)
        for state in states:
            for district in states[state].districts:
                for person in players:
                    district.setCampaigningThisTurn(person - 1, 0)
                    district.setAdsThisTurn(person - 1, 0)
    if currentDate <= numTurns:
        #showStartOfTurnReport()
        autoSave()
        top = Tk()
        global exit_status
        top.title("")
        msg = Message(top, text = 'Save and quit, or continue to {}\'s turn'.format(players[player].name))
        msg.pack()
        saveQuit = Button(top, text = 'Save', command = lambda:save_and_quit())
        saveQuit.pack()
        nextPlayer = Button(top, text = 'Continue to next player', command = lambda:next_player_button(top))
        nextPlayer.pack()
        center(top)
        top.mainloop()
        print(exit_status)
        if exit_status:
            exit()
        exit_status = False
    else:
        winner = 0
        mostDelegates = 0
        for person in players:
            if players[person].delegateCount > mostDelegates:
                winner = person
                mostDelegates = players[person].delegateCount
        player = 1

        showStartOfTurnReport()
        createNationalMap()            #show the map one last time to see the final results. 
        messagebox.showinfo("Winner", "The Winner is: " + str(players[winner].publicName))
        exit()

def next_player_button(top):
    #destroy the next turn Tk, and go on as usual
    top.quit()
    top.destroy()
    return

def calcEndTurn(fundraising):      #this will calculate the new resources available to the player
    resources = players[player].resources

    #time
    resources[0] = 80
    #money: remaining + fundraising + baseline + momentum + from states organization
    localFundraising = 0
    for state in states:
        #calculate % of population donating
        for district in states[state].districts:
            #expected range for number donating 0-.45 given support from 0-150
            numberDonating = 1 - (1.5 + states[state].organizations[player-1] / 10.0) ** (district.support[player - 1] / -50.0)
            localFundraising += numberDonating * district.population * 500 * (2 - math.exp(players[player].momentum / -50.0))

    localFundraising = round(localFundraising)
    resources[1] = resources[1] + fundraising * 4000 + 20000 + localFundraising
    players[player].momentum = players[player].momentum /2.0
    players[player].endTurn(currentDate, fundraising * 4000 + 20000, localFundraising)

def calculateStateOpinions():       #this function will calculate the opinion of each player in each state
    if currentDate == 0:       
        if players[1].isHuman == 'human':
            createNationalMap()
        else:
            calcAImove()

    else:               #each turn after that the new support is calculated. a player must be on the ballot (organization level 1) to get any support
        for i in range(len(players)):
            for state in states:
                org = states[state].organizations[i]
                for district in states[state].districts:
                    for date in calendarOfContests:             #in the 2 weeks before the election campaining is more effective
                        mult = 1
                        if date[0] == state and date[1] == currentDate - 1:
                            mult = 1.1
                        elif date[0] == state and date[1] == currentDate:
                            mult = 1.2
                    campaingingTime = district.campaigningThisTurn[i]
                    adBuy = district.adsThisTurn[i]
                    adsTotal = sum(district.adsThisTurn)
                    mult = (1 + float(players[i + 1].momentum) / 50.0) * mult

                    issueMult = 1
                    #for issue in range(len(issues)):       #only the issue in the news that week matters 
                    #print(eventOfTheWeek, district.positions[eventOfTheWeek], players[i+1].positions[eventOfTheWeek])
                    if district.positions[eventOfTheWeek] == 0:
                        pass

                    elif players[i+1].positions[eventOfTheWeek] == district.positions[eventOfTheWeek]:
                        issueMult += 0.33

                    else:
                        issueMult -= 0.16 * abs(players[i+1].positions[eventOfTheWeek] - district.positions[eventOfTheWeek])

                    if issueMult <= 0.25:       #shouldn't matter since only one issues is up at a time, so this shouldn't come into play, but just in case
                        issueMult = 0.25
                    mult = issueMult * mult 
                    support = campaingingTime*1.5 + org*2
                    support += float(adBuy) / float(adsTotal + 1) * (adsTotal / 100.0) ** (1.1/2.0)     #adbuy/add total - percentage of adds support player gets, second part is the amount of support created by the adds
                    support = support*mult
                    #the plus 1 is to avoid dividing by 0 when there is no advertising in a state
                    support = round(support)
                    district.setSupport(i, support)
                states[state].updateSupport(numPlayers, calendarOfContests, currentDate)

        #print(states["Iowa"].support)

def decideContests():
    global pastElections
    global weekResults
    momentums = []
    weekDelegates = {}
    weekResults = {}
    for i in range(numPlayers):
        momentums.append(0)
        weekDelegates[i+1] = 0
        weekResults[i+1] = {'delegates':0, 'states':[],'districts':[]}
    totalMomemtum = 50
    for state in calendarOfContests:
        if state[1] + 1 == currentDate:
            states[state[0]].calculatePollingAverage(calendarOfContests, currentDate)     #just in case it isn't up to date 

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
                totalVotes = 0
                for i in range(numPlayers):
                    if orgs[i] > 0:     #checking that player is on the ballot
                        votes = random.gauss(district.pollingAverage[i], 3)
                        votes = votes * district.population * 150000
                        totalVotes += votes
                        if votes < 0:
                            votes = 1
                            players[i + 1].momentum -= 2
                        if votes > mostVotes:
                            if winner != 0:
                                players[winner].momentum -= 1
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

                players[winner].delegateCount += districtDelegates
                weekDelegates[winner] += districtDelegates

                weekResults[winner]['delegates'] += districtDelegates
                weekResults[winner]['districts'].append(district.name)

                totalMomemtum += districtDelegates / 4.0
                momentums[winner - 1] += districtDelegates

            stateWinner = stateVotes.index(max(stateVotes)) + 1
            stateMostVotes = max(stateVotes)

            players[stateWinner].delegateCount += stateDelegates
            weekDelegates[stateWinner] += stateDelegates

            weekResults[winner]['delegates'] += stateDelegates
            weekResults[winner]['states'].append(stateName)

            totalMomemtum += stateDelegates / 2.0
            momentums[winner - 1] += stateDelegates

            pastElections[stateName] = stateWinner
            print(stateName, stateWinner, stateDelegates)


            votesCounts = ''
            stateVotesTotal = sum(stateVotes)
            for i in range(numPlayers):
                playerStateVotes = stateVotes[i]
                votesPercentage = round(float(playerStateVotes) / float(stateVotesTotal) * 100) 
                votesCounts += str(players[i+1].publicName) + ' wins ' + str(int(votesPercentage)) + ' precent of the vote, \n'
            

    weekResultString = ''
    for person in weekDelegates:
        weekResultString += players[person].publicName + ' with ' +str(weekDelegates[person]) + ' delegates; '


    #divy up the base momentum to the players based on how much of the state by state they won
    for i in range(len(momentums)):
        players[i+1].momentum += momentums[i] / float(sum(momentums)+.01) * totalMomemtum
    return

def calcAImove(agent):       #this will do the AI move, the agent will specify which AI to use, if I make more than one.
    global player
    global players
    global states
    global calendarOfContests
    global currentDate
    
    stateValues = [[],[]]
    districtValues = [[],[]]

    for state in states:
        #first calculate the value for each state
        for contest in calendarOfContests:
            if contest[0] == states[state].name:
                timeToElection = contest[1] - currentDate
        stateCloseness = max(states[state].support[:(player-1)] + states[state].support[(player):]) - states[state].support[player-1] #how close to the lead the AI is in the state
        stateDelegates = 0  

        for district in states[state].districts:
            districtDelegates = (district.population * 2) / 3
            stateDelegates += district.population - districtDelegates        #note, state delgates here is just the delgates awarded to the overall state winner. 
            closeness = max(district.support[:(player-1)] + district.support[(player):]) - district.support[player-1]
            closeness = 10*max(district.support[:(player-1)] + district.support[(player):]) / float(abs(closeness)+1)   
            #print('closeness: ', closeness)     
            districtValue = timeToElection + districtDelegates + closeness
            #print('district value: ', districtValue)
            #and the value for each district
            if timeToElection >=0:      #don't invest where the election has already passed
                districtValues[1].append(district)
                districtValues[0].append(districtValue)

        #determine where to build organization here first, based on a fixed threshold
        buildThreshold = 20
        if (9-timeToElection) * stateDelegates**1.2 > (states[state].organizations[player-1]+1) * buildThreshold:
            costToBuild = 10000*states[state].organizations[player-1]
            if costToBuild == 0:
                costToBuild = 10000
            if players[player].resources[1] > costToBuild:
                players[player].resources[1] -= costToBuild
                states[state].organizations[player-1] += 1
                print(state, 'build org', states[state].organizations[player-1])

        stateValue =  timeToElection + stateDelegates + stateCloseness
        stateValues[0].append(states[state].name)
        stateValues[1].append(stateValue)
        
    districtValues = [list(t) for t in zip(*sorted(zip(districtValues[0], districtValues[1])))]        #sort the districts by value
    #stateValues = [zip(*sorted(zip(stateValues[1], stateValues[0])))]        #and the states

    #determine where to spend resources
    while players[player].resources[1] > 1000:            #first spend the money       
        district = districtValues[1][-1]

        players[player].resources[1] -= 1000
        addBuyValue = district.adsThisTurn[player-1] + 1000
        district.setAdsThisTurn(player-1, addBuyValue)
        #print(district.name, 'add buy')

        districtValues[0][-1] -= 2
        districtValues = [list(t) for t in zip(*sorted(zip(districtValues[0], districtValues[1])))]        #as long as this resorting isn't super slow, these seems like a reasonable way to iterate through the districts. 
            

    while players[player].resources[0] > 0:        #then determine where to spend time
        district = districtValues[1][-1]

        if districtValues[0][-1] > 20:       #setting some value for switching to fundraising instead of campaining. Should possibly change over time (weight fundraising more heavily early in the game)
            players[player].resources[0] -= 1
            addBuyValue = district.campaigningThisTurn[player-1] + 1
            district.setCampaigningThisTurn(player-1, addBuyValue)
            districtValues[0][-1] -= 2
            #print(district.name, 'time spent')
            districtValues = [list(t) for t in zip(*sorted(zip(districtValues[0], districtValues[1])))]
        else:
            calcEndTurn(players[player].resources[0])
            players[player].resources[0] = 0
    #if all the hours are allocated with none on fundraising, end the turn. 
    calcEndTurn(0)

    if player < numPlayers:
        player += 1
    else: 
        calculateStateOpinions()
        currentDate += 1
        decideContests()
        player = 1
        eventOfTheWeek = random.randint(0,len(issueNames)-1)
        for state in states:
            for district in states[state].districts:
                for person in players:
                    district.setCampaigningThisTurn(person - 1, 0)
                    district.setAdsThisTurn(person - 1, 0)
    if currentDate <= numTurns:
        #showStartOfTurnReport()
        #autoSave()
        return
    else:
        winner = 0
        mostDelegates = 0
        for person in players:
            if players[person].delegateCount > mostDelegates:
                winner = person
                mostDelegates = players[person].delegateCount
        player = 1
        createNationalMap()         #show the map one last time to see the final results. 
        messagebox.showinfo("Winner", "The Winner is: " + str(players[winner].publicName))
        exit()

def save_and_quit():
    global exit_status
    exit_status = True
    saveGame()
    return 

def autoSave():
    #save in the oldest of 3 autosave files
    autosaveFiles = ['autosave','autosave2','autosave3']
    filePaths = []
    for fileName in autosaveFiles:
        filePath = os.getcwd()+'/CampaignSaves/'+fileName+'.save'
        filePaths.append(filePath)
        if not os.path.isfile(filePath):
            saveGameSecond(fileName, Tk(), True)
            return
    
    ages = []
    for fileName in filePaths:
        ages.append(os.stat(fileName).st_mtime)
    fileName = autosaveFiles[ages.index(min(ages))]
    saveGameSecond(fileName, Tk(), True)
    return

def saveGame():
    global player
    global currentDate
    global players
    global states
    global pastElections    

    autosave = False
    saveName = Tk()
    saveNameLabel = Label(saveName, text = "Name for the save file: ")
    saveNameLabel.pack()
    saveNameEntry = Entry(saveName)
    saveNameEntry.pack(side= RIGHT)
    saveButton = Button(saveName, text = "Save Game", command = lambda : saveGameSecond(saveNameEntry.get(), saveName, autosave))
    saveButton.pack()
    center(saveName)
    saveName.mainLoop()
    return

def saveGameSecond(fileName, window, autosave):
    global player
    global currentDate
    global players
    global states
    global pastElections
    window.destroy()
    saveFile = []
    saveFile.append(pickle.dumps(players))
    saveFile.append(pickle.dumps(states))
    saveFile.append(pickle.dumps(pastElections))
    saveFile.append(pickle.dumps(player))
    saveFile.append(pickle.dumps(currentDate))
    saveFile.append(pickle.dumps(weekResults))
    saveFile.append(pickle.dumps(numTurns))
    #try:
    pickle.dump(saveFile, open(os.getcwd()+ '/CampaignSaves/' + fileName + '.save', 'wb'))
    print(fileName)
    if not autosave:
            messagebox.showinfo("Save Succesful", "Save Succesful")
    #except:
    #    messagebox.showinfo("Save Failed", "Save Failed")
    return

def loadGame(window):
    global player
    global currentDate
    global players
    global states
    global pastElections   
    global numPlayers
    global weekResults 
    global numTurns

    window.destroy()
    root = Tk()
    root.withdraw()
    #file_path = filedialog.askopenfilename(initialdir = os.getcwd() + '\\saveGames\\',filetypes = [('save games', '.save')])
    file_path = filedialog.askopenfilename(initialdir = os.path.join(os.getcwd(), "..\\",'Google Drive\\CampaignSaves\\'),filetypes = [('save games', '.save')])
    root.destroy()
    
    # Check if user cancelled the dialog
    if not file_path or file_path == "":
        # Return to main menu if no file was selected
        mainMenu()
        return
    
    try:
        saveFile = pickle.load(open(file_path, 'rb'))
    except (FileNotFoundError, pickle.UnpicklingError, TypeError) as e:
        messagebox.showerror("Load Error", f"Failed to load save file: {str(e)}")
        mainMenu()
        return

    players = pickle.loads(saveFile[0])
    states = pickle.loads(saveFile[1])
    pastElections = pickle.loads(saveFile[2])
    player = pickle.loads(saveFile[3])
    currentDate = pickle.loads(saveFile[4])
    weekResults = pickle.loads(saveFile[5])
    try:
        numTurns = pickle.loads(saveFile[6])
    except IndexError:
        numTurns = 8
    
    setCalendar(numTurns)
    numPlayers = len(players)

    showStartOfTurnReport()
    createNationalMap()

def exitGame():
    sys.exit()

def returnColor(event):
    natMap = event.widget

    natMapImage = Image.open("nationalMap.png")
    mapPix = natMapImage.load()

    print(mapPix[event.x, event.y])

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
