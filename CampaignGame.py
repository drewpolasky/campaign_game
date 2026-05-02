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
import RemoteSaveLoad
import state_issues

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
issueNames = list(state_issues.ISSUE_NAMES)
eventOfTheWeek = random.randint(0,len(issueNames)-1)
headlineOfTheWeek = ''


def _refresh_headline():
    """Pick a flavor headline for the current eventOfTheWeek issue."""
    global headlineOfTheWeek
    issue = issueNames[eventOfTheWeek] if 0 <= eventOfTheWeek < len(issueNames) else ''
    pool = state_issues.ISSUE_HEADLINES.get(issue, [])
    if pool:
        headlineOfTheWeek = random.choice(pool)
    else:
        headlineOfTheWeek = 'Issue of the week: {}'.format(issue) if issue else ''


def _format_position(p, issue_index=None):
    """Friendly label for an issue position in {-1, 0, 1}.

    If issue_index is provided, use the issue-specific side labels
    (e.g. 'Pro-Choice' / 'Pro-Life'). Otherwise fall back to generic
    Support / Oppose / Neutral.
    """
    if issue_index is not None:
        return state_issues.side_label(issue_index, p)
    try:
        v = int(round(float(p)))
    except (TypeError, ValueError):
        return 'Neutral'
    if v > 0:
        return 'Support (+1)'
    if v < 0:
        return 'Oppose (-1)'
    return 'Neutral (0)'


_refresh_headline()
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
    mainMenuWindow.title('Campaign')

    w = 280
    h = 180
    ws = mainMenuWindow.winfo_screenwidth()
    hs = mainMenuWindow.winfo_screenheight()
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)
    mainMenuWindow.geometry('%dx%d+%d+%d' % (w, h, x, y))

    bgImage = Image.open("nationalMap.png").resize((w, h))
    bgPhoto = ImageTk.PhotoImage(bgImage)
    canvas = Canvas(mainMenuWindow, width=w, height=h, highlightthickness=0)
    canvas.pack(fill='both', expand=True)
    canvas.create_image(0, 0, anchor='nw', image=bgPhoto)
    canvas.bgPhoto = bgPhoto  # keep reference

    startGameButton = Button(mainMenuWindow, text='Start a New Game', command=lambda:setUpGame(mainMenuWindow))
    loadGameButton = Button(mainMenuWindow, text='Load Game', command=lambda:loadGame(mainMenuWindow))
    canvas.create_window(w/2, h/2 - 20, window=startGameButton)
    canvas.create_window(w/2, h/2 + 20, window=loadGameButton)

    mainMenuWindow.mainloop()

_TUTORIAL_PAGES = [
    {
        'title': 'Welcome to Campaign',
        'image': None,
        'body': (
            "You're running for president. The goal is simple: win more delegates than any other candidate by the end of the campaign calendar.\n\n"
            "Each week:\n"
            "  * Every candidate takes a turn deciding where to spend time and money.\n"
            "  * Whatever contests are scheduled for that week are decided at the end of the week.\n"
            "  * The campaign rolls forward and a new issue takes over the news cycle.\n\n"
            "This tutorial walks through the map, your resources, how support works, the issue system, and a few tips. Click 'Next' to move on, or 'Back to Main Menu' to skip out at any time."
        ),
    },
    {
        'title': 'The National Map',
        'image': 'tutorialNationalMap.jpg',
        'body': (
            "The center of every turn is the national map. Each state is shaded by who is currently leading in the polls there, or by who won if the contest has already taken place. White states are ones where no candidate has any support yet.\n\n"
            "Hover your mouse over a state to see a tooltip with:\n"
            "  * The state name and how many delegates it's worth.\n"
            "  * When it votes (this week, in N weeks, or already voted).\n"
            "  * The current leader and each player's polling percentage.\n"
            "  * The state's stance on whatever issue is in the news this week.\n\n"
            "Click a state to zoom into its district map and open the state focus panel on the right."
        ),
    },
    {
        'title': 'The Calendar (Left Sidebar)',
        'image': 'tutorialSidebar.png',
        'body': (
            "The left sidebar lists every contest in chronological order:\n"
            "  * 'Iowa - wk 4 (12 del)' shows the state, the week it votes, and the delegates at stake.\n"
            "  * Rows where you're already on the ballot are highlighted green and prefixed with '*'.\n"
            "  * Past contests are grayed out as '[Done]'.\n\n"
            "Each row also has a quick-action button on the right:\n"
            "  * 'Ballot $10k' if you're not on the ballot yet.\n"
            "  * 'Office $10k' to grow from level 1 to level 2.\n"
            "  * 'Build $20k' (or higher) to keep building your organization.\n\n"
            "There's also a 'Jump to State' search box at the top so you can find a state by name without scrolling."
        ),
    },
    {
        'title': 'Your Resources',
        'image': 'tutorialDashboard.png',
        'body': (
            "You start each week with 80 hours of candidate time and your remaining money (everyone starts with $100,000).\n\n"
            "Time gets spent on either:\n"
            "  * Campaigning - direct in-district support gain.\n"
            "  * Fundraising - converted to cash at $4,000 per hour, plus a $20,000 baseline each week.\n\n"
            "Money pays for two things:\n"
            "  * Ad buys in specific districts.\n"
            "  * Building organization in a state.\n\n"
            "Momentum is shown on the dashboard. You earn it by winning contests; bigger wins on quieter weeks (e.g. Iowa) give more momentum than wins on super-Tuesday-style weeks. Momentum boosts both your support gains and your local fundraising, but it fades fast if you stop winning."
        ),
    },
    {
        'title': 'Building Support in a State',
        'image': 'tutorialStateZoom.jpg',
        'body': (
            "Click into a state and the right panel becomes the State Focus. From there each district has two sliders: campaigning time and ad buys.\n\n"
            "Each turn, the support you gain in a district is roughly:\n"
            "    (organization tier x 2) + (campaign hours x 1.5) + share-of-ad-spend bonus\n"
            "  ...all multiplied by some bonuses:\n"
            "  * +10% the week before the election, +20% on election week.\n"
            "  * Momentum amplifies everything (+x% scales with your current momentum).\n"
            "  * Issue alignment with the state on the issue of the week: +33% if you match, smaller penalty if you clash.\n\n"
            "When you're done planning, hit 'Save Ad Buys & Campaign Time'. That commits the spend and bounces you back to the national overview."
        ),
    },
    {
        'title': 'Organization (Getting on the Ballot)',
        'image': None,
        'body': (
            "Before you can earn any support in a state, you need to be on the ballot there. That's organization tier 1, which costs $10,000.\n\n"
            "Each tier above 1 also costs $10,000 x current tier (so $10k for the office, $20k for the next, $30k after that, etc). Higher tiers:\n"
            "  * Multiply support gained from organization directly (each tier adds 2 baseline support per district per turn).\n"
            "  * Boost local donations from supporters.\n"
            "  * Improve voter turnout for you on election night.\n\n"
            "You can build organization until the contest is over - the deadline is the end of voting week, not before. Past that the 'Ballot' button is hidden because it's too late."
        ),
    },
    {
        'title': 'Issues and the Issue of the Week',
        'image': None,
        'body': (
            "If you start the game in Issues Mode, each candidate picks a stance on 7 issues during setup: Climate Action, Abortion, Taxes & Spending, Gun Policy, Healthcare, Regulation, and Trade. The setup screen shows how many delegates worth of states currently take each side, so you can see the tradeoffs.\n\n"
            "Every week the news cycle picks one issue to dominate. You can see it on the Campaign Dashboard with a flavor headline. While that issue is in the news:\n"
            "  * If your stance matches the state's, support builds 33% faster there.\n"
            "  * If you clash with the state, support builds slower (worse the further apart you are).\n"
            "  * If the state is neutral on that issue, no bonus or penalty.\n\n"
            "State stances are calibrated to real-world political leanings and roughly balanced across all states - meaning each side of an issue covers a similar number of total delegates."
        ),
    },
    {
        'title': 'Ending Your Turn',
        'image': None,
        'body': (
            "On the dashboard, set the 'Fundraising time allocation' slider to whatever portion of your remaining hours should go to fundraising. The rest goes unused (only allocated campaign hours actually count).\n\n"
            "Hit 'End Turn' and play passes to the next candidate. Once everyone has gone:\n"
            "  * The week's contests are decided. Delegates are awarded based on the polling average plus a small random factor at election time, scaled by population and turnout.\n"
            "  * Wins give momentum to the winners and reset some district allocations.\n"
            "  * The week ticks forward, a new issue takes over the news, and play returns to the first candidate.\n\n"
            "If all candidates are AI you'll see a per-week recap screen so you can step through the campaign without skipping straight to the final results."
        ),
    },
    {
        'title': 'Saving and Loading',
        'image': None,
        'body': (
            "From the main menu you can:\n"
            "  * 'Start a New Game' or 'Resume Current Game' if a save is in progress.\n"
            "  * 'Load Game' from a local save file.\n"
            "  * 'Load from Server' to grab a save from the configured remote server.\n"
            "  * 'Sync Saves with Server' to push and pull the local Saves folder to/from the server. Newer file wins.\n\n"
            "During gameplay there's also a Save button on the top header. The game autosaves into rotating slots (autosave / autosave2 / autosave3) at the end of each week."
        ),
    },
    {
        'title': 'Strategy Tips',
        'image': None,
        'body': (
            "A few things that aren't obvious from the rules:\n\n"
            "  * Imminent contests pay off the most. Spending in week 9 on a state voting in week 11 is more efficient than spending it in week 4.\n"
            "  * Closeness matters. Pouring resources into a state you're already winning by 30 has diminishing returns; the closeness penalty goes the other way too.\n"
            "  * Get on the ballot early in big states. You don't earn any support until you're at organization tier 1.\n"
            "  * Hold cash for the final wave. Money compounds via fundraising hours and momentum, so a big late push often beats steady spending.\n"
            "  * Match issues to your map. If you're targeting blue/red states heavily, pick stances that match. The setup screen's delegate counts per side are your guide.\n\n"
            "When you're ready, hit 'Back to Main Menu' below and 'Start a New Game'. Good luck on the trail."
        ),
    },
]


def _show_tutorial_page(index):
    index = max(0, min(index, len(_TUTORIAL_PAGES) - 1))
    page = _TUTORIAL_PAGES[index]
    root, body = build_screen(
        'Tutorial - {}/{}: {}'.format(index + 1, len(_TUTORIAL_PAGES), page['title']),
        'A walk through the rules of Campaign. You can leave at any time.')

    outer = Frame(body, bg='#f3efe2')
    outer.pack(fill='both', expand=True)
    canvas = Canvas(outer, bg='#f3efe2', highlightthickness=0)
    scroll = Scrollbar(outer, orient='vertical', command=canvas.yview)
    inner = Frame(canvas, bg='#f3efe2')
    inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.create_window((0, 0), window=inner, anchor='nw')
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    canvas.bind('<Enter>', lambda e: _bound_to_mousewheel(e, canvas))
    canvas.bind('<Leave>', lambda e: _unbound_to_mousewheel(e, canvas))

    if page.get('image'):
        try:
            img = Image.open(page['image'])
            max_w = 900
            iw, ih = img.size
            if iw > max_w:
                scale = max_w / float(iw)
                img = img.resize((int(iw * scale), int(ih * scale)), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            ui_state['tutorial_image'] = photo
            Label(inner, image=photo, bg='#f3efe2').pack(anchor='w', pady=(0, 12))
        except (IOError, OSError):
            pass

    text_card = Frame(inner, bg='white', bd=1, relief='solid', padx=14, pady=12)
    text_card.pack(fill='x', pady=(0, 16))
    Label(text_card, text=page['title'], bg='white',
          font=('TkDefaultFont', 14, 'bold'), justify=LEFT).pack(anchor='w')
    Label(text_card, text=page['body'], bg='white', justify=LEFT,
          wraplength=900, font=('TkDefaultFont', 10)).pack(anchor='w', pady=(8, 0))

    nav = Frame(inner, bg='#f3efe2')
    nav.pack(anchor='w', pady=(0, 12))
    if index > 0:
        Button(nav, text='< Back', command=lambda: _show_tutorial_page(index - 1), padx=14).pack(side='left')
    if index < len(_TUTORIAL_PAGES) - 1:
        Button(nav, text='Next >', command=lambda: _show_tutorial_page(index + 1), padx=14).pack(side='left', padx=8)
    else:
        Button(nav, text='Finish', command=mainMenu, padx=14).pack(side='left', padx=8)
    Button(nav, text='Back to Main Menu', command=mainMenu, padx=14).pack(side='left', padx=8)

    progress = Frame(inner, bg='#f3efe2')
    progress.pack(anchor='w')
    Label(progress, text='Step {} of {}'.format(index + 1, len(_TUTORIAL_PAGES)),
          bg='#f3efe2', fg='#555555').pack(anchor='w')


def tutorial(window=None):
    """Entry point for the tutorial. window arg kept for backward compat."""
    try:
        if window is not None and hasattr(window, 'destroy'):
            window.destroy()
    except Exception:
        pass
    _show_tutorial_page(0)

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

    # Apply real-world calibrated state-level positions on each issue.
    for stateName, st in states.items():
        st.positions = state_issues.get_state_positions(stateName)

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
    except KeyError:
        pass
    for line in pixelList:
        l = line.split(',')
        state = l[2].strip()
        if state.lower() == stateName.lower():
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

    players[player].resources[0] -= fundraising     #this and the next line could be combined, but in case I come back later and change things, this should be more clear
    fundraising += players[player].resources[0]     #add any left over hours to the fundraising time
    calcEndTurn(fundraising)

    if player < numPlayers:
        player += 1
    else: 
        calculateStateOpinions()
        currentDate += 1
        decideContests()
        player = 1
        eventOfTheWeek = random.randint(0,len(issueNames)-1)
        _refresh_headline()
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
    # Compute the time/money this player actually committed to campaigning
    # and ads this turn (district allocations are reset only when the week
    # rolls over, so they're still accurate here).
    campaign_hours = 0
    ad_spend = 0
    for s in states:
        for d in states[s].districts:
            try:
                campaign_hours += d.campaigningThisTurn[player - 1]
                ad_spend += d.adsThisTurn[player - 1]
            except (IndexError, TypeError):
                pass
    players[player].endTurn(currentDate, fundraising * 4000 + 20000, localFundraising,
                            fundraisingHours=fundraising,
                            campaigningHours=campaign_hours,
                            adSpend=ad_spend)

def calculateStateOpinions():       #this function will calculate the opinion of each player in each state
    if currentDate == 0:       
        if players[1].isHuman == 'human':
            createNationalMap()
        else:
            calcAImove(players[1].isHuman)

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

                    # Issue-of-the-week alignment uses the STATE's position
                    # (one position per state for now). If the player's stance
                    # matches the state, building support is easier this week;
                    # if it clashes, harder. Disabled in non-issues mode.
                    issueMult = 1
                    state_pos = 0
                    if issuesMode:
                        try:
                            state_pos = states[state].positions[eventOfTheWeek]
                        except (IndexError, AttributeError, TypeError):
                            state_pos = 0
                    pp_list = players[i + 1].positions or []
                    player_pos = pp_list[eventOfTheWeek] if 0 <= eventOfTheWeek < len(pp_list) else 0
                    if state_pos == 0:
                        pass  # state has no strong stance, no bonus or penalty
                    elif player_pos == state_pos:
                        issueMult += 0.33
                    else:
                        issueMult -= 0.16 * abs(player_pos - state_pos)

                    if issueMult <= 0.25:
                        issueMult = 0.25
                    mult = issueMult * mult
                    # Break support into its three sources so we can show a
                    # per-source breakdown in the end-of-game report.
                    org_support = org * 2 * mult
                    campaign_support = campaingingTime * 1.5 * mult
                    ad_support = (float(adBuy) / float(adsTotal + 1)) * (adsTotal / 100.0) ** (1.1 / 2.0) * mult
                    support = org_support + campaign_support + ad_support
                    try:
                        players[i + 1].addStat('support_from_org', org_support)
                        players[i + 1].addStat('support_from_campaign', campaign_support)
                        players[i + 1].addStat('support_from_ads', ad_support)
                    except AttributeError:
                        pass
                    #the plus 1 is to avoid dividing by 0 when there is no advertising in a state
                    support = round(support)
                    district.setSupport(i, support)
                states[state].updateSupport(numPlayers, calendarOfContests, currentDate)

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
                try:
                    players[winner].addStat('districts_won', 1)
                except AttributeError:
                    pass

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
            try:
                players[stateWinner].addStat('states_won', stateName)
            except AttributeError:
                pass


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

def _ai_personality(player_number):
    """Return a stable, per-AI personality dict. Same player always gets the
    same personality; different AIs get different priorities."""
    rng = random.Random(0xC0FFEE + player_number * 31)
    return {
        'urgency': rng.uniform(0.85, 1.35),       # how much they chase imminent contests
        'closeness': rng.uniform(0.75, 1.35),     # how much they fight for swing districts
        'delegates': rng.uniform(0.75, 1.30),     # how much they value big-state delegates
        'fundraise_cutoff': rng.uniform(9.0, 16.0),   # below this score, fundraise instead
        'org_threshold': rng.uniform(13.0, 24.0),     # tolerance for building orgs
        'noise': rng.uniform(0.18, 0.32),         # per-district random spread
    }


def _score_district(district, timeToElection, stateDelegates, ai_idx, personality, rng):
    """Score how valuable spending one more unit of resource on this district is.
    Higher is better. Designed to favor close races, near-term elections,
    delegate-rich states, and districts where we already have a base of support.
    A small per-call random factor plus the AI's personality weights make
    each AI play a bit differently from week to week."""
    if timeToElection < 0:
        return 0.0  # contest already happened — never spend here

    support = district.support
    my_support = support[ai_idx]
    others = support[:ai_idx] + support[ai_idx+1:]
    top_other = max(others) if others else 0

    # Margin: positive means we are behind by that much, negative means ahead.
    margin = top_other - my_support
    closeness = 100.0 / (1.0 + abs(margin) ** 1.2)

    # Sharpened urgency curve: this week's contests dominate the planner.
    if timeToElection == 0:
        urgency = 2.4
    elif timeToElection == 1:
        urgency = 1.7
    elif timeToElection <= 3:
        urgency = 1.1
    elif timeToElection <= 6:
        urgency = 0.6
    else:
        urgency = 0.3

    delegates = (district.population / 3.0) + (stateDelegates / 6.0)

    # Don't pile resources where we are already crushing everyone.
    if margin < -25:
        runaway_penalty = 0.4
    elif margin < -10:
        runaway_penalty = 0.7
    else:
        runaway_penalty = 1.0

    base = (
        personality['urgency'] * urgency *
        (personality['closeness'] * closeness + personality['delegates'] * delegates)
        * runaway_penalty
    )
    # Stochastic kick: jitter scores so two AIs don't always converge on the
    # same district even with identical state. Multiplier centered on 1.0.
    spread = personality['noise']
    jitter = rng.uniform(1.0 - spread, 1.0 + spread)
    return base * jitter


def calcAImove(agent):
    """AI turn: build organization where it matters, then allocate ads, time,
    and fundraising hours by greedy scoring. Then advance the turn."""
    global player
    global players
    global states
    global calendarOfContests
    global currentDate
    global eventOfTheWeek
    global numTurns
    global numPlayers

    ai_idx = player - 1
    personality = _ai_personality(player)
    # Per-turn RNG: stable jitter with a seed mixing player + week so every
    # AI gets fresh random kicks each turn but two AIs in the same week still
    # diverge from each other.
    rng = random.Random(0xBEEF * player + currentDate * 7919)

    # Build per-state info (delegates, time to election). Skip states whose
    # contest has already happened so the AI never wastes resources there.
    state_info = {}
    for state_name, state in states.items():
        time_to_election = None
        for contest in calendarOfContests:
            if contest[0] == state_name:
                time_to_election = contest[1] - currentDate
                break
        if time_to_election is None or time_to_election < 0:
            continue  # no upcoming contest -> ignore entirely
        state_delegates = 0
        for district in state.districts:
            state_delegates += district.population - (district.population * 2) / 3
        state_info[state_name] = {
            'time': time_to_election,
            'delegates': state_delegates,
            'state': state,
        }

    # 1) Build organizations where the upside is high enough.
    for state_name, info in state_info.items():
        time_to_election = info['time']
        if time_to_election > 8:
            continue
        state = info['state']
        org_level = state.organizations[ai_idx]
        cost = max(10000, 10000 * org_level)
        # Value of an org tick: scales with delegates and how soon we vote.
        org_value = info['delegates'] * (1.0 + max(0, 6 - time_to_election))
        threshold = (org_level + 1) * personality['org_threshold']
        if org_value > threshold and players[player].resources[1] >= cost:
            players[player].resources[1] -= cost
            state.organizations[ai_idx] += 1
            try:
                players[player].addStat('org_money_total', int(cost))
                players[player].addStat('orgs_built', 1)
            except AttributeError:
                pass

    # 2) Build a flat list of scored districts for spending. Use a stable
    # numeric tie-breaker (id) so we never compare District objects directly.
    scored = []  # list of [score, tie, district, state_name]
    for state_name, info in state_info.items():
        for district in info['state'].districts:
            score = _score_district(district, info['time'], info['delegates'], ai_idx, personality, rng)
            scored.append([score, id(district), district, state_name])

    if not scored:
        # Nothing to invest in (e.g. all elections passed): bank the rest.
        calcEndTurn(players[player].resources[0])
        players[player].resources[0] = 0
        _ai_advance_turn()
        return

    def best():
        # Highest score wins; ties broken by id (stable).
        return max(range(len(scored)), key=lambda i: (scored[i][0], scored[i][1]))

    # 3) Spend ad money on the best districts. Each $1000 yields diminishing returns.
    AD_CHUNK = 1000
    while players[player].resources[1] >= AD_CHUNK:
        i = best()
        score, _, district, _ = scored[i]
        if score <= 0:
            break
        district.setAdsThisTurn(ai_idx, district.adsThisTurn[ai_idx] + AD_CHUNK)
        players[player].resources[1] -= AD_CHUNK
        # Diminishing returns plus a small fresh jitter on each chunk.
        scored[i][0] = score * 0.85 * rng.uniform(0.95, 1.05)

    # 4) Spend time. Campaigning vs fundraising decision is per-hour:
    # if no district has score above this AI's personality fundraise cutoff,
    # fundraise the rest.
    fundraise_cutoff = personality['fundraise_cutoff']
    fundraising_hours = 0
    while players[player].resources[0] > 0:
        i = best()
        score = scored[i][0]
        if score < fundraise_cutoff:
            fundraising_hours += players[player].resources[0]
            players[player].resources[0] = 0
            break
        district = scored[i][2]
        district.setCampaigningThisTurn(ai_idx, district.campaigningThisTurn[ai_idx] + 1)
        players[player].resources[0] -= 1
        # Diminishing returns per hour, plus a small fresh jitter so the
        # planner doesn't lock onto one district forever.
        scored[i][0] = score * 0.9 * rng.uniform(0.95, 1.05)

    # 5) End turn (handles fundraising income and resource refresh).
    calcEndTurn(fundraising_hours)
    _ai_advance_turn()


def _ai_advance_turn():
    """Advance to the next player or roll the week, mirroring endTurn() side effects."""
    global player, numPlayers, currentDate, eventOfTheWeek, states, players, numTurns
    if player < numPlayers:
        player += 1
        return
    calculateStateOpinions()
    currentDate += 1
    decideContests()
    player = 1
    eventOfTheWeek = random.randint(0, len(issueNames) - 1)
    for state in states:
        for district in states[state].districts:
            for person in players:
                district.setCampaigningThisTurn(person - 1, 0)
                district.setAdsThisTurn(person - 1, 0)


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


app_root = None
app_window = None
current_modal = None
pixel_lookup = None
ui_state = {
    'selected_state': None,
    'map_label': None,
    'map_photo': None,
    'fundraising_var': None,
    'resource_labels': {},
    'state_panel_parent': None,
    'calendar_listbox': None,
    'calendar_items': [],
    'search_var': None,
    'search_status_var': None,
}
menu_resume_state = {
    'selected_state': None,
}


def debug_launch(message):
    try:
        line = '[launch] {}'.format(message)
        with open('launch_debug.log', 'a') as debug_file:
            debug_file.write(line + '\n')
    except Exception:
        pass


def init_app_root():
    global app_root
    global app_window
    debug_launch('init_app_root entered')
    root_exists = app_root is not None and app_root.winfo_exists()
    window_exists = app_window is not None and app_window.winfo_exists()
    if (not root_exists) or (not window_exists):
        debug_launch('creating Tk root and visible Toplevel window')
        app_root = Tk()
        app_root.withdraw()
        app_window = Toplevel(app_root)
        screen_w = app_window.winfo_screenwidth()
        screen_h = app_window.winfo_screenheight()
        width = min(1480, max(1100, screen_w - 120))
        height = min(920, max(720, screen_h - 120))
        pointer_x = app_window.winfo_pointerx()
        pointer_y = app_window.winfo_pointery()
        pos_x = max(pointer_x - (width // 2), 0)
        pos_y = max(pointer_y - 80, 0)
        debug_launch('screen={}x{}, root={}x{}, pointer=({}, {}), pos=({}, {})'.format(screen_w, screen_h, width, height, pointer_x, pointer_y, pos_x, pos_y))
        app_window.geometry('{}x{}+{}+{}'.format(width, height, pos_x, pos_y))
        app_window.minsize(1000, 700)
        app_window.configure(bg='#f3efe2')
        app_window.protocol('WM_DELETE_WINDOW', exitGame)
        app_window.bind('<Control-s>', lambda event: saveGame())
        app_window.bind('<Escape>', lambda event: close_modal())
        app_window.update_idletasks()
        debug_launch('window geometry after idle={} mapped={} viewable={}'.format(app_window.geometry(), app_window.winfo_ismapped(), app_window.winfo_viewable()))
        force_root_visible(app_window)
        app_window.after(100, lambda: force_root_visible(app_window))
        app_window.after(400, lambda: force_root_visible(app_window))
    else:
        debug_launch('reusing existing app window with geometry={}'.format(app_window.geometry()))
        force_root_visible(app_window)
    return app_window


def close_modal():
    global current_modal
    if current_modal is not None and current_modal.winfo_exists():
        current_modal.destroy()
    current_modal = None


def force_root_visible(root=None):
    if root is None:
        root = app_window if app_window is not None else app_root
    if root is None:
        debug_launch('force_root_visible called with no root')
        return
    try:
        debug_launch('force_root_visible start state={} geometry={} mapped={} viewable={}'.format(root.state(), root.geometry(), root.winfo_ismapped(), root.winfo_viewable()))
        root.deiconify()
        root.lift()
        root.update()
        debug_launch('force_root_visible end state={} geometry={} mapped={} viewable={}'.format(root.state(), root.geometry(), root.winfo_ismapped(), root.winfo_viewable()))
    except TclError as err:
        debug_launch('force_root_visible TclError={}'.format(err))


def clear_root(title):
    root = init_app_root()
    close_modal()
    root.title(title)
    for child in root.winfo_children():
        child.destroy()
    for key in ui_state:
        if isinstance(ui_state[key], dict):
            ui_state[key] = {}
        elif isinstance(ui_state[key], list):
            ui_state[key] = []
        else:
            ui_state[key] = None
    return root


def build_screen(title, subtitle='', gameplay=False):
    root = clear_root(title)
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    width = min(1480, max(1100, screen_w - 120))
    height = min(920, max(720, screen_h - 120))
    x = max(int((screen_w - width) / 2), 0)
    y = max(int((screen_h - height) / 2), 0)
    try:
        root.minsize(1000, 700)
    except Exception:
        pass
    root.geometry('{}x{}+{}+{}'.format(width, height, x, y))
    outer = Frame(root, bg='#f3efe2')
    outer.pack(fill='both', expand=True)

    header = Frame(outer, bg='#143642', padx=22, pady=18)
    header.pack(fill='x')
    Label(header, text=title, bg='#143642', fg='white', font=('TkDefaultFont', 17, 'bold')).pack(anchor='w')
    if subtitle:
        Label(header, text=subtitle, bg='#143642', fg='#d7e8ed', font=('TkDefaultFont', 10)).pack(anchor='w', pady=(4, 0))
    if gameplay:
        build_game_nav(header)

    body = Frame(outer, bg='#f3efe2', padx=18, pady=18)
    body.pack(fill='both', expand=True)
    return root, body


def build_game_nav(parent):
    nav = Frame(parent, bg='#143642')
    nav.pack(anchor='e', pady=(10, 0))
    Button(nav, text='Main Menu', command=open_main_menu_from_game, padx=10).pack(side='left', padx=4)
    Button(nav, text='National Map', command=createNationalMap, padx=10).pack(side='left', padx=4)
    Button(nav, text='Turn Report', command=showStartOfTurnReport, padx=10).pack(side='left', padx=4)
    Button(nav, text='Save', command=saveGame, padx=10).pack(side='left', padx=4)
    Button(nav, text='Load', command=lambda: loadGame(None), padx=10).pack(side='left', padx=4)
    Button(nav, text='End Turn', command=lambda: endTurn(None, ui_state['fundraising_var'].get() if ui_state['fundraising_var'] else 0), padx=10).pack(side='left', padx=4)


def make_card(parent, title):
    frame = Frame(parent, bg='white', bd=1, relief='groove')
    Label(frame, text=title, bg='white', fg='#143642', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w', padx=12, pady=(10, 4))
    return frame


def get_pixel_lookup():
    global pixel_lookup
    if pixel_lookup is None:
        pixel_lookup = {}
        pixel_file = open('pixelList.txt', 'r')
        for line in pixel_file:
            l = line.split(',')
            try:
                pixel_lookup[(int(l[0]), int(l[1]))] = l[2].strip()
            except (IndexError, ValueError):
                pass
    return pixel_lookup


def get_state_name_from_pixel(xLoc, yLoc):
    return get_pixel_lookup().get((xLoc, yLoc), None)


def _is_all_ai_game():
    return bool(players) and all(players[p].isHuman != 'human' for p in players)


def start_active_turn_flow(show_report=True):
    if currentDate > numTurns:
        show_final_results()
        return

    if _is_all_ai_game():
        run_one_ai_week()
        return

    while currentDate <= numTurns and players[player].isHuman != 'human':
        calcAImove(players[player].isHuman)

    if currentDate > numTurns:
        show_final_results()
    elif show_report and currentDate > 1 and players[player].isHuman == 'human':
        showStartOfTurnReport()
    else:
        createNationalMap()


def run_one_ai_week():
    """Run AI moves until the week rolls over, then show a spectator screen."""
    start_date = currentDate
    while currentDate == start_date and currentDate <= numTurns and _is_all_ai_game():
        calcAImove(players[player].isHuman)
    if currentDate > numTurns:
        show_final_results()
        return
    show_ai_week_screen()


def show_ai_week_screen():
    """All-AI mode: show last week's results plus the national map, with a Next Week button."""
    root, body = build_screen('Week {} - AI Match'.format(currentDate),
                              'All candidates are AI controlled. Review last week, then continue.')

    shell = Frame(body, bg='#f3efe2')
    shell.pack(fill='both', expand=True)
    left = Frame(shell, bg='#f3efe2', width=380)
    left.pack(side='left', fill='y', padx=(0, 12))
    left.pack_propagate(False)
    right = Frame(shell, bg='#f3efe2')
    right.pack(side='left', fill='both', expand=True)

    headline_card = make_card(left, 'In the News')
    headline_card.pack(fill='x', pady=(0, 12))
    issue_label = issueNames[eventOfTheWeek] if 0 <= eventOfTheWeek < len(issueNames) else ''
    Label(headline_card, text=headlineOfTheWeek or issue_label,
          bg='white', font=('TkDefaultFont', 11, 'bold'),
          justify=LEFT, wraplength=340).pack(anchor='w', padx=12, pady=(0, 4))
    Label(headline_card, text='Issue of the week: {}'.format(issue_label),
          bg='white', justify=LEFT, wraplength=340).pack(anchor='w', padx=12, pady=(0, 8))

    standings = make_card(left, 'Standings')
    standings.pack(fill='x', pady=(0, 12))
    for person in players:
        line = '{}: {} delegates, momentum {:.0f}'.format(
            players[person].publicName or 'Player {}'.format(person),
            players[person].delegateCount,
            players[person].momentum)
        Label(standings, text=line, bg='white', justify=LEFT, wraplength=340).pack(anchor='w', padx=12, pady=2)

    results_card = make_card(left, 'Last Week Results')
    results_card.pack(fill='both', expand=True, pady=(0, 12))
    if not weekResults:
        Label(results_card, text='No contests were resolved last week.', bg='white', justify=LEFT, wraplength=340).pack(anchor='w', padx=12, pady=(0, 12))
    else:
        for person in weekResults:
            person_frame = Frame(results_card, bg='white', bd=1, relief='solid', padx=10, pady=6)
            person_frame.pack(fill='x', padx=12, pady=4)
            Label(person_frame, text=players[person].publicName or 'Player {}'.format(person),
                  bg='white', font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')
            for resultType, value in weekResults[person].items():
                if isinstance(value, (int, float)):
                    display = str(value)
                else:
                    display = ', '.join(value) if value else '(none)'
                Label(person_frame, text='{}: {}'.format(resultType, display),
                      bg='white', justify=LEFT, wraplength=320).pack(anchor='w', pady=1)

    Button(left, text='Run Next Week' if currentDate <= numTurns else 'See Final Results',
           command=run_one_ai_week, padx=14).pack(anchor='w', pady=(8, 0))

    map_card = make_card(right, 'National Map')
    map_card.pack(fill='both', expand=True)
    natMapImage = Image.open('nationalMap.jpg')
    natMapImage = paintNationalMap(natMapImage)
    natMapImg = ImageTk.PhotoImage(natMapImage)
    ui_state['map_photo'] = natMapImg
    map_label = Label(map_card, image=natMapImg, bg='white')
    map_label.pack(padx=12, pady=(0, 8))
    attach_state_tooltip(map_label)


def has_game_in_progress():
    return len(players) > 0 and currentDate <= numTurns


def open_main_menu_from_game():
    menu_resume_state['selected_state'] = ui_state.get('selected_state')
    mainMenu()


def resume_current_game():
    if not has_game_in_progress():
        mainMenu()
        return
    if currentDate > numTurns:
        show_final_results()
        return
    if players[player].isHuman == 'human':
        createNationalMap(menu_resume_state.get('selected_state'))
    else:
        start_active_turn_flow(True)

def show_turn_transition_screen():
    subtitle = 'Everything for this turn is locked in. Move on when you are ready.'
    root, body = build_screen('Turn Complete', subtitle)

    card = make_card(body, 'Next Up')
    card.pack(fill='x', pady=(0, 16))
    Label(card, text='{} is up for week {}.'.format(players[player].publicName, currentDate), bg='white', justify=LEFT, wraplength=900).pack(anchor='w', padx=12, pady=(0, 12))

    actions = Frame(body, bg='#f3efe2')
    actions.pack(anchor='w')
    Button(actions, text='Continue', command=lambda: start_active_turn_flow(True), padx=14).pack(side='left')
    Button(actions, text='Save Game', command=saveGame, padx=14).pack(side='left', padx=8)
    Button(actions, text='Save and Exit', command=save_and_quit, padx=14).pack(side='left')


def update_map_selection(stateName):
    rows = ui_state.get('calendar_rows') or {}
    for name, row in rows.items():
        try:
            if name == stateName:
                row.configure(highlightthickness=2, highlightbackground='#1f5f8b')
            else:
                row.configure(highlightthickness=0)
        except Exception:
            pass


def select_state_from_calendar(event=None, state_name=None):
    if state_name:
        createNationalMap(state_name)


def _build_org_from_sidebar(stateName, cost):
    """Wrapper for the calendar-row Build button: keep the player's current
    view (national overview vs. zoomed district map) instead of always
    jumping into the state's district map after building."""
    prior_selection = ui_state.get('selected_state')
    starting_resources = players[player].resources[1]
    getOnBallot(player, stateName, cost, None, None)
    spent = starting_resources != players[player].resources[1]
    # If the build went through, getOnBallot will have re-rendered into the
    # state's district view. Bounce back to the prior view if we weren't
    # already focused on this state.
    if spent and prior_selection != stateName:
        createNationalMap(prior_selection if prior_selection else None)


def search_for_state(event=None):
    query = ''
    if ui_state['search_var'] is not None:
        query = ui_state['search_var'].get().strip().lower()
    if not query:
        if ui_state['search_status_var'] is not None:
            ui_state['search_status_var'].set('')
        return

    exact = None
    partial = None
    for stateName in states:
        lowered = stateName.lower()
        if lowered == query:
            exact = stateName
            break
        if partial is None and lowered.startswith(query):
            partial = stateName
    result = exact or partial
    if result is None:
        if ui_state['search_status_var'] is not None:
            ui_state['search_status_var'].set('No state matched that search.')
        return
    if ui_state['search_status_var'] is not None:
        ui_state['search_status_var'].set('Jumped to {}.'.format(result))
    createNationalMap(result)


def update_resource_summary():
    labels = ui_state['resource_labels']
    if not labels:
        return
    resources = players[player].resources
    labels['resources'].set('Time: {}    Money: ${:,}'.format(resources[0], int(resources[1])))
    labels['momentum'].set('Momentum: {}'.format(round(players[player].momentum, 1)))
    issue_label = issueNames[eventOfTheWeek]
    your_pos = _format_position(players[player].positions[eventOfTheWeek] if players[player].positions else 0, eventOfTheWeek)
    labels['issue'].set('Headline:\n  {}\nIssue: {}\nYour stance: {}'.format(headlineOfTheWeek or issue_label, issue_label, your_pos))
    standings = []
    for person in players:
        standings.append('{}: {} delegates'.format(players[person].publicName, players[person].delegateCount))
    labels['standings'].set('\n'.join(standings))


def main():
    global player
    global currentDate
    global players
    global states
    global pastElections
    global weekResults
    global pixel_lookup
    try:
        Path('launch_debug.log').write_text('')
    except Exception:
        pass
    debug_launch('main entered')
    players = {}
    states = {}
    pastElections = {}
    weekResults = {}
    pixel_lookup = None
    player = 1
    currentDate = 1
    debug_launch('calling setUpStates')
    setUpStates()
    debug_launch('setUpStates completed with {} states'.format(len(states)))
    root = init_app_root()
    debug_launch('init_app_root returned state={} geometry={} mapped={} viewable={}'.format(root.state(), root.geometry(), root.winfo_ismapped(), root.winfo_viewable()))

    splash = Frame(root, bg='#f3efe2')
    splash.pack(fill='both', expand=True)
    Label(splash, text='Loading Campaign...', bg='#f3efe2', fg='#143642', font=('TkDefaultFont', 18, 'bold')).pack(pady=40)
    Label(splash, text='If you can see this, the root window is opening correctly.', bg='#f3efe2', fg='#143642').pack()
    root.update_idletasks()
    debug_launch('splash packed mapped={} viewable={} geometry={}'.format(root.winfo_ismapped(), root.winfo_viewable(), root.geometry()))

    force_root_visible(root)
    root.after(0, mainMenu)
    root.after(100, lambda: force_root_visible(root))
    root.after(400, lambda: force_root_visible(root))
    debug_launch('entering mainloop')
    root.mainloop()


def mainMenu():
    debug_launch('mainMenu entered')
    root = init_app_root()
    close_modal()
    root.title('Campaign')
    for child in root.winfo_children():
        child.destroy()

    w, h = 520, 440
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = int((ws - w) / 2)
    y = int((hs - h) / 2)
    root.geometry('{}x{}+{}+{}'.format(w, h, x, y))
    try:
        root.minsize(w, h)
    except Exception:
        pass

    canvas = Canvas(root, width=w, height=h, highlightthickness=0)
    canvas.pack(fill='both', expand=True)
    bgImage = Image.open('nationalMap.png').resize((w, h))
    bgPhoto = ImageTk.PhotoImage(bgImage)
    canvas.create_image(0, 0, anchor='nw', image=bgPhoto)
    canvas.bgPhoto = bgPhoto  # keep reference

    canvas.create_text(w/2, 36, text='Campaign',
                       font=('TkDefaultFont', 22, 'bold'), fill='white')

    buttons = []
    if has_game_in_progress():
        buttons.append(('Resume Current Game', resume_current_game))
    buttons.append(('Start a New Game', setUpGame))
    buttons.append(('Tutorial', lambda: tutorial(None)))
    buttons.append(('Load Game', lambda: loadGame(None)))
    buttons.append(('Load from Server', loadGameRemote))
    buttons.append(('Sync Saves with Server', lambda: syncRemoteSaves(False)))
    buttons.append(('Exit', exitGame))

    start_y = h - (len(buttons) * 38) - 20
    for i, (label, cmd) in enumerate(buttons):
        btn = Button(root, text=label, command=cmd, width=22)
        canvas.create_window(w/2, start_y + i * 38, window=btn)

    debug_launch('mainMenu map layout packed children={} geometry={}'.format(len(root.winfo_children()), root.geometry()))
    root.update()


def setUpGame(window=None):
    root, body = build_screen('New Game Setup', 'Pick the campaign rules, then move through player setup in this same window.')

    setup_card = make_card(body, 'Campaign Settings')
    setup_card.pack(fill='x', pady=(0, 16))

    mode = IntVar(value=1)
    turnsVar = IntVar(value=8)
    playersVar = IntVar(value=2)

    Label(setup_card, text='Issue mode', bg='white').pack(anchor='w', padx=12)
    Radiobutton(setup_card, text='No Issues Mode', variable=mode, value=1, bg='white').pack(anchor='w', padx=16)
    Radiobutton(setup_card, text='Issues Mode', variable=mode, value=2, bg='white').pack(anchor='w', padx=16)

    Label(setup_card, text='Number of turns', bg='white').pack(anchor='w', padx=12, pady=(8, 0))
    OptionMenu(setup_card, turnsVar, 8, 10, 20).pack(anchor='w', padx=12)

    Label(setup_card, text='Number of players', bg='white').pack(anchor='w', padx=12, pady=(8, 0))
    Scale(setup_card, variable=playersVar, orient=HORIZONTAL, from_=2, to_=10, bg='white').pack(anchor='w', padx=12)

    Button(setup_card, text='Continue to Player Setup', command=lambda: setUpPlayers(playersVar.get(), None, mode.get(), turnsVar.get()), padx=14).pack(anchor='w', padx=12, pady=(12, 14))


def setUpPlayers(numP, setUpWindow, mode, numTurn_menu):
    global numPlayers
    global issuesMode
    global numTurns
    global player
    global players

    players = {}
    numTurns = numTurn_menu
    issuesMode = (mode == 2)
    player = 1
    setCalendar(numTurns)

    numPlayers = numP
    for i in range(numPlayers):
        newPlayer = Player(i + 1)
        players[i + 1] = newPlayer
        for state in states:
            states[state].setOrganization(i, 0)
            for district in states[state].districts:
                district.setSupport(i, 0)
                district.setCampaigningThisTurn(i, 0)
                district.setAdsThisTurn(i, 0)
    for state in states:
        states[state].updateSupport(numPlayers, calendarOfContests, currentDate)

    setUpPlayer(mode)


def setUpPlayer(mode):
    root, body = build_screen('Player {} Setup'.format(player), 'Configure each candidate without leaving the main window.')

    setup_card = make_card(body, 'Candidate Profile')
    setup_card.pack(fill='x')

    Label(setup_card, text='Candidate name', bg='white').pack(anchor='w', padx=12)
    name = Entry(setup_card, width=30)
    name.pack(anchor='w', padx=12, pady=(0, 10))

    isHuman = StringVar(value='human')
    Label(setup_card, text='Controller', bg='white').pack(anchor='w', padx=12)
    OptionMenu(setup_card, isHuman, 'human', 'AI').pack(anchor='w', padx=12, pady=(0, 10))

    issueVars = []
    if mode == 2:
        # Delegate-weighted balance per side, computed from the actual loaded
        # state delegate counts so the player can see the trade-offs.
        delegate_totals = {name: sum(d.population for d in st.districts)
                           for name, st in states.items()}
        balance = state_issues.compute_balance(delegate_totals)

        issue_card = make_card(body, 'Issue Positions')
        issue_card.pack(fill='x', pady=(16, 0))
        Label(issue_card, text='Pick a stance for each issue. Aligning with a state grants a campaign bonus when that issue is in the news. Numbers show total delegates whose state takes that side.',
              bg='white', justify=LEFT, wraplength=620).pack(anchor='w', padx=12, pady=(0, 8))
        for idx, issue in enumerate(state_issues.ISSUES):
            issue_balance = balance.get(issue['name'], {'support': 0, 'oppose': 0, 'neutral': 0})
            row = Frame(issue_card, bg='white')
            row.pack(fill='x', padx=12, pady=4)
            Label(row, text=issue['name'], bg='white', font=('TkDefaultFont', 10, 'bold'), width=18, anchor='w').pack(side='left')
            var = IntVar(value=0)
            issueVars.append(var)
            side_counts = {
                'con': issue_balance['oppose'],
                'mid': issue_balance['neutral'],
                'pro': issue_balance['support'],
            }
            for value, key in [(-1, 'con'), (0, 'mid'), (1, 'pro')]:
                Radiobutton(row,
                            text='{} ({} del)'.format(issue[key], int(side_counts[key])),
                            variable=var, value=value, bg='white').pack(side='left', padx=4)

    Button(body, text='Save Player and Continue',
           command=lambda: setPositions([v.get() for v in issueVars], name.get(), isHuman.get(), None, mode),
           padx=14).pack(anchor='w', pady=(16, 0))


def setPositions(issues, name, isHuman, setUpPlayerWindow, mode):
    global player
    person = players[player]
    person.setPositions(issues)
    person.setHuman(isHuman)
    person.setName(name if name else 'Player {}'.format(player))
    if player < numPlayers:
        player += 1
        setUpPlayer(mode)
    else:
        player = 1
        # State-level positions are loaded once in setUpStates() from
        # state_issues.STATE_POSITIONS. If issues mode is off, blank them out
        # so no issue alignment math triggers. District-level positions are
        # initialized to zeros (district-level positions may be reintroduced
        # later, but for now only state positions drive gameplay).
        if not issuesMode:
            for state in states:
                states[state].positions = [0 for _ in range(len(issueNames))]
        for state in states:
            for district in states[state].districts:
                district.setPositions([0 for _ in range(len(issueNames))])

        calculateStateOpinions()
        start_active_turn_flow(False)

def render_selected_state(stateName):
    panel_parent = ui_state['state_panel_parent']
    if panel_parent is None:
        return
    for child in panel_parent.winfo_children():
        child.destroy()

    if not stateName or stateName not in states:
        placeholder = make_card(panel_parent, 'State Detail')
        placeholder.pack(fill='both', expand=True)
        Label(placeholder, text='Select a state from the map, the calendar, or the search box to plan district-level actions without opening a separate window.', bg='white', justify=LEFT, wraplength=360).pack(anchor='w', padx=12, pady=(0, 12))
        return

    ui_state['selected_state'] = stateName
    update_map_selection(stateName)

    currentState = states[stateName]
    state_card = make_card(panel_parent, '{} Focus'.format(stateName))
    state_card.pack(fill='both', expand=True)

    currentOrg = currentState.organizations[player - 1]
    delegates = 0
    for district in currentState.districts:
        delegates += district.population

    Label(state_card, text='Organization level: {}    Delegates at stake: {}'.format(currentOrg, int(delegates)), bg='white', justify=LEFT, wraplength=360).pack(anchor='w', padx=12, pady=(0, 6))

    polling_lines = []
    for person in range(numPlayers):
        polling_lines.append('{} polling: {}'.format(players[person + 1].publicName, currentState.pollingAverage[person]))
    Label(state_card, text='\n'.join(polling_lines), bg='white', justify=LEFT, wraplength=360).pack(anchor='w', padx=12, pady=(0, 10))

    # Issue-of-the-week alignment summary for this state.
    try:
        state_pos = currentState.positions[eventOfTheWeek]
    except (IndexError, AttributeError, TypeError):
        state_pos = 0
    your_pos = players[player].positions[eventOfTheWeek] if players[player].positions else 0
    if state_pos == 0:
        align_text = "{} has no strong stance - no bonus or penalty this week.".format(stateName)
    elif your_pos == state_pos:
        align_text = "Your stance matches {} - support builds faster here this week.".format(stateName)
    else:
        align_text = "Your stance clashes with {} - support builds slower here this week.".format(stateName)
    Label(state_card,
          text='Issue of the week: {}\n  Your stance: {}    {} stance: {}\n  {}'.format(
              issueNames[eventOfTheWeek], _format_position(your_pos, eventOfTheWeek),
              stateName, _format_position(state_pos, eventOfTheWeek), align_text),
          bg='white', justify=LEFT, wraplength=360).pack(anchor='w', padx=12, pady=(0, 10))

    if currentOrg == 0:
        Button(state_card, text='Get on the ballot ($10,000)', command=lambda: getOnBallot(player, stateName, 10000, None, None)).pack(anchor='w', padx=12, pady=(0, 8))
    elif currentOrg == 1:
        Button(state_card, text='Build field office ($10,000)', command=lambda: getOnBallot(player, stateName, 10000, None, None)).pack(anchor='w', padx=12, pady=(0, 8))
    else:
        Button(state_card, text='Build more organization (${:,.0f})'.format(10000 * currentOrg), command=lambda: getOnBallot(player, stateName, 10000 * currentOrg, None, None)).pack(anchor='w', padx=12, pady=(0, 8))

    scroll_holder = Frame(state_card, bg='white')
    scroll_holder.pack(fill='both', expand=True, padx=12, pady=(0, 6))
    canvas = Canvas(scroll_holder, bg='white', highlightthickness=0)
    scrollbar = Scrollbar(scroll_holder, orient='vertical', command=canvas.yview)
    inner = Frame(canvas, bg='white')
    inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.create_window((0, 0), window=inner, anchor='nw')
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')
    canvas.bind('<Enter>', lambda e: _bound_to_mousewheel(e, canvas))
    canvas.bind('<Leave>', lambda e: _unbound_to_mousewheel(e, canvas))

    addBuys = []
    campaigningTime = []
    allocatedTime = 0
    allocatedMoney = 0
    for district in currentState.districts:
        allocatedTime += district.campaigningThisTurn[player - 1]
        allocatedMoney += district.adsThisTurn[player - 1]

    budgetTime = players[player].resources[0] + allocatedTime
    budgetMoney = players[player].resources[1] + allocatedMoney
    summaryVar = StringVar()

    def update_budget_label(*args):
        totalAdCosts = sum(slider.get() for slider in addBuys)
        totalTime = sum(slider.get() for slider in campaigningTime)
        timeLeft = budgetTime - totalTime
        moneyLeft = budgetMoney - totalAdCosts
        summaryVar.set('Planned time: {} / {}    Planned ads: ${:,} / ${:,}    Remaining: {} time, ${:,}'.format(totalTime, budgetTime, int(totalAdCosts), int(budgetMoney), timeLeft, int(moneyLeft)))

    def clear_plan():
        for slider in addBuys:
            slider.set(0)
        for slider in campaigningTime:
            slider.set(0)
        update_budget_label()

    def even_split(scales):
        total = sum(scale.get() for scale in scales)
        if total <= 0 or len(scales) == 0:
            return
        base = int(total / len(scales))
        remainder = total - base * len(scales)
        for index, scale in enumerate(scales):
            scale.set(base + (1 if index < remainder else 0))
        update_budget_label()

    Label(state_card, textvariable=summaryVar, bg='white', justify=LEFT, wraplength=360).pack(anchor='w', padx=12, pady=(0, 8))

    preset_bar = Frame(state_card, bg='white')
    preset_bar.pack(fill='x', padx=12, pady=(0, 8))
    Button(preset_bar, text='Clear Plan', command=clear_plan).pack(side='left')
    Button(preset_bar, text='Even Time Split', command=lambda: even_split(campaigningTime)).pack(side='left', padx=6)
    Button(preset_bar, text='Even Ad Split', command=lambda: even_split(addBuys)).pack(side='left')

    for district in currentState.districts:
        dBg = _get_district_leader_color(district)
        district_frame = Frame(inner, bg=dBg, bd=1, relief='solid', padx=8, pady=8)
        district_frame.pack(fill='x', pady=4)
        Label(district_frame, text='{} - {} delegates'.format(district.name, int(district.population)), bg=dBg, font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')

        district_polling = []
        for person in range(numPlayers):
            district_polling.append('{}: {}%'.format(players[person + 1].publicName, district.pollingAverage[person]))
        Label(district_frame, text=' | '.join(district_polling), bg=dBg, justify=LEFT, wraplength=320).pack(anchor='w', pady=(2, 6))

        ad_slider = Scale(district_frame, label='Ad buys', from_=0, to=budgetMoney, resolution=1000, orient=HORIZONTAL, bg=dBg, highlightthickness=0, command=lambda value: update_budget_label())
        time_slider = Scale(district_frame, label='Campaigning time', from_=0, to=budgetTime, orient=HORIZONTAL, bg=dBg, highlightthickness=0, command=lambda value: update_budget_label())
        ad_slider.set(district.adsThisTurn[player - 1])
        time_slider.set(district.campaigningThisTurn[player - 1])
        time_slider.pack(fill='x')
        ad_slider.pack(fill='x')
        campaigningTime.append(time_slider)
        addBuys.append(ad_slider)

    update_budget_label()

    actions = Frame(state_card, bg='white')
    actions.pack(fill='x', padx=12, pady=(4, 12))
    Button(actions, text='Save Ad Buys & Campaign Time', command=lambda: backToMap(None, campaigningTime, stateName, allocatedTime, allocatedMoney, addBuys), padx=12).pack(side='left')
    Button(actions, text='Back to Overview', command=createNationalMap, padx=12).pack(side='left', padx=8)


def showStartOfTurnReport():
    if currentDate <= 1 or players[player].isHuman != 'human':
        createNationalMap()
        return

    root, body = build_screen('Week {} Briefing'.format(currentDate), 'Review last week, then head straight back to the national map.', gameplay=True)

    fundraisingIncome = players[player].history[currentDate - 1]['fundraisingIncome']
    localIncome = players[player].history[currentDate - 1]['localIncome']

    headline_card = make_card(body, 'In the News This Week')
    headline_card.pack(fill='x', pady=(0, 16))
    issue_label = issueNames[eventOfTheWeek] if 0 <= eventOfTheWeek < len(issueNames) else ''
    Label(headline_card, text=headlineOfTheWeek or issue_label,
          bg='white', font=('TkDefaultFont', 13, 'bold'),
          justify=LEFT, wraplength=900).pack(anchor='w', padx=12, pady=(0, 4))
    Label(headline_card, text='Issue: {}  -  Your stance: {}'.format(
              issue_label,
              _format_position(players[player].positions[eventOfTheWeek] if players[player].positions else 0, eventOfTheWeek)),
          bg='white', justify=LEFT, wraplength=900).pack(anchor='w', padx=12, pady=(0, 10))

    summary = make_card(body, 'At a Glance')
    summary.pack(fill='x', pady=(0, 16))
    summary_lines = [
        'Candidate: {}'.format(players[player].publicName),
        'Total income last week: ${:,}'.format(int(fundraisingIncome + localIncome)),
        'Fundraising income: ${:,}'.format(int(fundraisingIncome)),
        'Local income: ${:,}'.format(int(localIncome)),
    ]
    for line in summary_lines:
        Label(summary, text=line, bg='white', justify=LEFT, wraplength=920).pack(anchor='w', padx=12, pady=2)

    results_card = make_card(body, 'Last Week Results')
    results_card.pack(fill='x', pady=(0, 16))
    if not weekResults:
        Label(results_card, text='No contests were resolved last week.', bg='white').pack(anchor='w', padx=12, pady=(0, 12))
    else:
        for person in weekResults:
            person_frame = Frame(results_card, bg='white', bd=1, relief='solid', padx=10, pady=8)
            person_frame.pack(fill='x', padx=12, pady=6)
            Label(person_frame, text=players[person].publicName, bg='white', font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')
            for resultType in weekResults[person].keys():
                value = weekResults[person][resultType]
                if isinstance(value, (int, float)):
                    display = str(value)
                else:
                    display = ', '.join(value)
                Label(person_frame, text='{}: {}'.format(resultType, display), bg='white', justify=LEFT, wraplength=860).pack(anchor='w', pady=1)

    actions = Frame(body, bg='#f3efe2')
    actions.pack(anchor='w')
    Button(actions, text='Continue to Map', command=createNationalMap, padx=14).pack(side='left')
    if calendarOfContests:
        Button(actions, text='Open Next Contest State', command=lambda: createNationalMap(calendarOfContests[0][0]), padx=14).pack(side='left', padx=8)


_pixel_state_cache = None
_pixel_district_cache = {}  # state_name -> {(x,y): district_name}


def get_pixel_district_map(stateName):
    """Lazy-load the (x, y) -> district name dict for one state."""
    if stateName in _pixel_district_cache:
        return _pixel_district_cache[stateName]
    mapping = {}
    for ext in ('txt',):
        path = os.path.join(os.getcwd(), 'stateDistricts', stateName + '.' + ext)
        if os.path.isfile(path):
            try:
                with open(path, 'r') as f:
                    for line in f:
                        parts = line.split(',')
                        if len(parts) >= 4:
                            try:
                                x = int(parts[0])
                                y = int(parts[1])
                            except ValueError:
                                continue
                            mapping[(x, y)] = parts[3].strip()
            except IOError:
                pass
            break
    _pixel_district_cache[stateName] = mapping
    return mapping


def format_district_tooltip(stateName, districtName):
    if stateName not in states:
        return '{} - {}'.format(stateName, districtName)
    state = states[stateName]
    district = None
    for d in state.districts:
        if d.name.strip().lower() == districtName.strip().lower():
            district = d
            break
    if district is None:
        return '{}\n(no data)'.format(districtName)
    lines = ['{} - {} delegates'.format(district.name, int(district.population))]
    support = district.support if district.support else []
    polling = district.pollingAverage if district.pollingAverage else []
    if support and any(s != 0 for s in support):
        total = float(sum(support)) or 1.0
        leader_idx = support.index(max(support))
        lines.append('Leader: {}'.format(players[leader_idx + 1].publicName or 'Player ' + str(leader_idx + 1)))
        for i, s in enumerate(support):
            name = players[i + 1].publicName or 'Player ' + str(i + 1)
            pct = 100.0 * s / total
            poll_str = ''
            if i < len(polling):
                poll_str = '  (polling {}%)'.format(polling[i])
            lines.append('  {}: {:.1f}% support{}'.format(name, pct, poll_str))
    else:
        lines.append('No support yet')
    return '\n'.join(lines)


def attach_district_tooltip(widget, stateName, scale):
    """Bind hover tooltips to the zoomed state map widget.

    scale: ratio of displayed image size to original (e.g. 0.6 if downscaled).
    Used to translate event.x/y back to original-image coords for the lookup.
    """
    state_tt = {'tw': None, 'last': None}

    def hide():
        if state_tt['tw'] is not None:
            try:
                state_tt['tw'].destroy()
            except Exception:
                pass
            state_tt['tw'] = None
        state_tt['last'] = None

    def show(districtName, x_root, y_root):
        hide()
        tw = Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry('+{}+{}'.format(x_root + 15, y_root + 15))
        Label(tw, text=format_district_tooltip(stateName, districtName), justify='left',
              background='#ffffe0', relief='solid', borderwidth=1,
              font=('TkDefaultFont', 9)).pack(ipadx=3, ipady=2)
        state_tt['tw'] = tw
        state_tt['last'] = districtName

    def on_motion(event):
        pixmap = get_pixel_district_map(stateName)
        if not pixmap:
            return
        # Translate widget coords -> original image coords.
        img = ui_state.get('map_photo')
        img_w = img.width() if img is not None else widget.winfo_width()
        img_h = img.height() if img is not None else widget.winfo_height()
        off_x = max(0, (widget.winfo_width() - img_w) // 2)
        off_y = max(0, (widget.winfo_height() - img_h) // 2)
        local_x = event.x - off_x
        local_y = event.y - off_y
        if scale and scale > 0:
            ox = int(round(local_x / scale))
            oy = int(round(local_y / scale))
        else:
            ox = local_x
            oy = local_y
        districtName = pixmap.get((ox, oy))
        if districtName is None:
            # Try a small radius in case rounding lands on a line pixel.
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    districtName = pixmap.get((ox + dx, oy + dy))
                    if districtName is not None:
                        break
                if districtName is not None:
                    break
        if districtName is None:
            hide()
            return
        if districtName != state_tt['last']:
            show(districtName, event.x_root, event.y_root)
        elif state_tt['tw'] is not None:
            state_tt['tw'].wm_geometry('+{}+{}'.format(event.x_root + 15, event.y_root + 15))

    widget.bind('<Motion>', on_motion)
    widget.bind('<Leave>', lambda e: hide())


def get_pixel_state_map():
    global _pixel_state_cache
    if _pixel_state_cache is None:
        _pixel_state_cache = {}
        try:
            with open('pixelList.txt', 'r') as f:
                for line in f:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        try:
                            _pixel_state_cache[(int(parts[0]), int(parts[1]))] = parts[2].strip()
                        except ValueError:
                            continue
        except IOError:
            pass
    return _pixel_state_cache


def format_state_tooltip(stateName):
    if stateName not in states:
        return stateName
    st = states[stateName]
    support = list(st.support) if st.support else []
    total_delegates = sum(d.population for d in st.districts)
    contest_week = None
    for contest in calendarOfContests:
        if contest[0] == stateName:
            contest_week = contest[1]
            break
    if contest_week is None:
        when = ''
    elif contest_week < currentDate:
        when = '  (voted week {})'.format(contest_week)
    elif contest_week == currentDate:
        when = '  (votes this week)'
    else:
        when = '  (votes week {}, in {})'.format(contest_week, contest_week - currentDate)
    lines = ['{} ({} delegates){}'.format(stateName, int(total_delegates), when)]
    if support:
        total = float(sum(support)) or 1.0
        leader_idx = support.index(max(support))
        lines.append('Leader: {}'.format(players[leader_idx + 1].publicName or ('Player ' + str(leader_idx + 1))))
        for i, s in enumerate(support):
            name = players[i + 1].publicName or ('Player ' + str(i + 1))
            pct = 100.0 * s / total
            lines.append('  {}: {:.1f}%'.format(name, pct))
    else:
        lines.append('No polling data yet')
    if issuesMode:
        try:
            state_pos = st.positions[eventOfTheWeek]
        except (IndexError, AttributeError, TypeError):
            state_pos = 0
        lines.append('{} on {}: {}'.format(stateName, issueNames[eventOfTheWeek], _format_position(state_pos, eventOfTheWeek)))
    return '\n'.join(lines)


def attach_state_tooltip(widget):
    state_tt = {'tw': None, 'last': None}

    def hide():
        if state_tt['tw'] is not None:
            try:
                state_tt['tw'].destroy()
            except Exception:
                pass
            state_tt['tw'] = None
        state_tt['last'] = None

    def show(stateName, x_root, y_root):
        hide()
        tw = Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry('+{}+{}'.format(x_root + 15, y_root + 15))
        Label(tw, text=format_state_tooltip(stateName), justify='left',
              background='#ffffe0', relief='solid', borderwidth=1,
              font=('TkDefaultFont', 9)).pack(ipadx=3, ipady=2)
        state_tt['tw'] = tw
        state_tt['last'] = stateName

    def on_motion(event):
        pixmap = get_pixel_state_map()
        img = getattr(widget, 'image', None) or ui_state.get('map_photo')
        img_w = img.width() if img is not None else widget.winfo_width()
        img_h = img.height() if img is not None else widget.winfo_height()
        off_x = max(0, (widget.winfo_width() - img_w) // 2)
        off_y = max(0, (widget.winfo_height() - img_h) // 2)
        px = event.x - off_x
        py = event.y - off_y
        stateName = pixmap.get((px, py))
        if stateName is None:
            hide()
            return
        if stateName != state_tt['last']:
            show(stateName, event.x_root, event.y_root)
        elif state_tt['tw'] is not None:
            state_tt['tw'].wm_geometry('+{}+{}'.format(event.x_root + 15, event.y_root + 15))

    widget.bind('<Motion>', on_motion)
    widget.bind('<Leave>', lambda e: hide())


def createNationalMap(selected_state=None):
    if players[player].isHuman != 'human':
        start_active_turn_flow(True)
        return

    root, body = build_screen("{}'s Turn".format(players[player].publicName), 'Use the calendar, search, or map to move between states without leaving this screen.', gameplay=True)

    shell = Frame(body, bg='#f3efe2')
    shell.pack(fill='both', expand=True)
    left = Frame(shell, bg='#f3efe2', width=340)
    left.pack(side='left', fill='y', padx=(0, 12))
    left.pack_propagate(False)
    center_frame = Frame(shell, bg='#f3efe2')
    center_frame.pack(side='left', fill='both', expand=True)
    right = Frame(shell, bg='#f3efe2', width=420)
    right.pack(side='left', fill='y', padx=(12, 0))
    right.pack_propagate(False)

    calendar_card = make_card(left, 'Calendar and Search')
    calendar_card.pack(fill='both', expand=True)

    Label(calendar_card, text='Search for a state', bg='white').pack(anchor='w', padx=12)
    searchVar = StringVar()
    ui_state['search_var'] = searchVar
    entry = Entry(calendar_card, textvariable=searchVar)
    entry.pack(fill='x', padx=12, pady=(0, 6))
    entry.bind('<Return>', search_for_state)
    Button(calendar_card, text='Jump to State', command=search_for_state).pack(anchor='w', padx=12)
    statusVar = StringVar(value='')
    ui_state['search_status_var'] = statusVar
    Label(calendar_card, textvariable=statusVar, bg='white', fg='#555555', justify=LEFT, wraplength=220).pack(anchor='w', padx=12, pady=(6, 10))

    Label(calendar_card, text='Upcoming contests', bg='white').pack(anchor='w', padx=12)
    list_outer = Frame(calendar_card, bg='white')
    list_outer.pack(fill='both', expand=True, padx=12, pady=(6, 12))
    list_canvas = Canvas(list_outer, bg='white', highlightthickness=0)
    list_scroll = Scrollbar(list_outer, orient='vertical', command=list_canvas.yview)
    list_inner = Frame(list_canvas, bg='white')
    list_inner.bind('<Configure>', lambda e: list_canvas.configure(scrollregion=list_canvas.bbox('all')))
    list_canvas.create_window((0, 0), window=list_inner, anchor='nw')
    list_canvas.configure(yscrollcommand=list_scroll.set)
    list_canvas.pack(side='left', fill='both', expand=True)
    list_scroll.pack(side='right', fill='y')
    list_canvas.bind('<Enter>', lambda e: _bound_to_mousewheel(e, list_canvas))
    list_canvas.bind('<Leave>', lambda e: _unbound_to_mousewheel(e, list_canvas))

    ui_state['calendar_listbox'] = None  # legacy hook no longer used
    ui_state['calendar_items'] = []
    ui_state['calendar_rows'] = {}       # state_name -> row Frame for highlight

    for contest in calendarOfContests:
        stateName = contest[0]
        date = contest[1]
        if stateName in states:
            delegates = int(sum(d.population for d in states[stateName].districts))
            try:
                org_level = states[stateName].organizations[player - 1]
            except (IndexError, TypeError):
                org_level = 0
        else:
            delegates = 0
            org_level = 0
        on_ballot = org_level > 0
        past = date < currentDate
        this_week = date == currentDate

        bg = '#d6f0c2' if on_ballot else 'white'
        if past:
            bg = '#e6e6e6'
        row = Frame(list_inner, bg=bg, bd=1, relief='solid')
        row.pack(fill='x', pady=1)
        ui_state['calendar_rows'][stateName] = row

        prefix = '[Done] ' if past else ('[Now] ' if this_week else '')
        ballot_marker = '* ' if on_ballot else ''
        label_text = '{}{}{} - wk {} ({} del)'.format(prefix, ballot_marker, stateName, date, delegates)
        # Click anywhere on the label opens the state.
        name_btn = Button(row, text=label_text, anchor='w', relief='flat',
                          bg=bg, activebackground='#cbe2c2',
                          command=lambda s=stateName: select_state_from_calendar(state_name=s))
        name_btn.pack(side='left', fill='x', expand=True)

        # Right-side action button: build organization. Skipped for past contests.
        if not past and stateName in states:
            cost = max(10000, 10000 * org_level)
            if org_level == 0:
                action_text = 'Ballot $10k'
            elif org_level == 1:
                action_text = 'Office $10k'
            else:
                action_text = 'Build ${}k'.format(int(cost / 1000))
            Button(row, text=action_text, padx=2,
                   command=lambda s=stateName, c=cost: _build_org_from_sidebar(s, c)).pack(side='right', padx=2, pady=1)

        ui_state['calendar_items'].append(stateName)

    map_title = 'National Map'
    map_note = 'Click a state to edit district spending. The selected state plan will appear in the right panel instead of opening a separate window.'
    if selected_state and selected_state in states:
        map_title = '{} District Map'.format(selected_state)
        map_note = 'You are zoomed into {}. Use Back to Overview to return to the national map while keeping the state plan on the right.'.format(selected_state)

    map_card = make_card(center_frame, map_title)
    map_card.pack(fill='both', expand=True)

    if selected_state and selected_state in states:
        path = os.getcwd()
        try:
            centerImage = Image.open(os.path.join(path, 'stateDistricts', selected_state + '.jpeg'))
        except IOError:
            centerImage = Image.open(path + '/stateDistricts/' + selected_state + '.jpeg')
        centerImage = paintStateMap(centerImage, selected_state)
        # Constrain state map so very wide states (e.g. Tennessee) don't push
        # the right sidebar offscreen. Preserve aspect ratio.
        max_w, max_h = 700, 560
        iw, ih = centerImage.size
        scale = min(max_w / float(iw), max_h / float(ih), 1.0)
        if scale < 1.0:
            # Use NEAREST so painted district pixels stay crisp and don't blur
            # into adjacent uncolored / line pixels during downscale.
            centerImage = centerImage.resize((int(iw * scale), int(ih * scale)), Image.NEAREST)
        centerImg = ImageTk.PhotoImage(centerImage)
        ui_state['map_photo'] = centerImg
        map_label = Label(map_card, image=centerImg, bg='white')
        map_label.pack(padx=12, pady=(0, 8))
        attach_district_tooltip(map_label, selected_state, scale)
        back_bar = Frame(map_card, bg='white')
        back_bar.pack(fill='x', padx=12, pady=(0, 8))
        Button(back_bar, text='Back to National Map', command=createNationalMap).pack(side='left')
    else:
        natMapImage = Image.open('nationalMap.jpg')
        natMapImage = paintNationalMap(natMapImage)
        natMapImg = ImageTk.PhotoImage(natMapImage)
        ui_state['map_photo'] = natMapImg
        map_label = Label(map_card, image=natMapImg, bg='white')
        map_label.pack(fill='both', expand=True, padx=12, pady=(0, 8))
        map_label.bind('<Button-1>', zoomToState)
        attach_state_tooltip(map_label)

    ui_state['map_label'] = map_label
    Label(map_card, text=map_note, bg='white', justify=LEFT, wraplength=640).pack(anchor='w', padx=12, pady=(0, 12))

    zoomed = bool(selected_state and selected_state in states)
    if not zoomed:
        dashboard = make_card(right, 'Campaign Dashboard')
        dashboard.pack(fill='x', pady=(0, 12))
        resourceVar = StringVar()
        momentumVar = StringVar()
        issueVar = StringVar()
        standingsVar = StringVar()
        ui_state['resource_labels'] = {
            'resources': resourceVar,
            'momentum': momentumVar,
            'issue': issueVar,
            'standings': standingsVar,
        }
        Label(dashboard, textvariable=resourceVar, bg='white', justify=LEFT, wraplength=240).pack(anchor='w', padx=12, pady=2)
        Label(dashboard, textvariable=momentumVar, bg='white', justify=LEFT, wraplength=240).pack(anchor='w', padx=12, pady=2)
        Label(dashboard, textvariable=issueVar, bg='white', justify=LEFT, wraplength=240).pack(anchor='w', padx=12, pady=2)
        Label(dashboard, text='Standings', bg='white', font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', padx=12, pady=(8, 0))
        Label(dashboard, textvariable=standingsVar, bg='white', justify=LEFT, wraplength=240).pack(anchor='w', padx=12, pady=(0, 8))

        fundraisingVar = IntVar(value=0)
        ui_state['fundraising_var'] = fundraisingVar
        Label(dashboard, text='Fundraising time allocation', bg='white').pack(anchor='w', padx=12)
        Scale(dashboard, variable=fundraisingVar, orient=HORIZONTAL, from_=0, to=players[player].resources[0], bg='white').pack(fill='x', padx=12)

        action_bar = Frame(dashboard, bg='white')
        action_bar.pack(fill='x', padx=12, pady=(6, 12))
        Button(action_bar, text='Review Report', command=showStartOfTurnReport).pack(side='left')
        Button(action_bar, text='End Turn', command=lambda: endTurn(None, fundraisingVar.get())).pack(side='left', padx=8)

        this_week = make_card(right, 'This Week')
        this_week.pack(fill='x', pady=(0, 12))
        upcoming = []
        for contest in calendarOfContests:
            if contest[1] == currentDate:
                upcoming.append(contest[0])
        if upcoming:
            Label(this_week, text='Voting this week: {}'.format(', '.join(upcoming)), bg='white', justify=LEFT, wraplength=360).pack(anchor='w', padx=12, pady=(0, 12))
        else:
            Label(this_week, text='No contests are scheduled to vote this week.', bg='white', justify=LEFT, wraplength=360).pack(anchor='w', padx=12, pady=(0, 12))

    state_container = Frame(right, bg='#f3efe2')
    state_container.pack(fill='both', expand=True)
    ui_state['state_panel_parent'] = state_container

    update_resource_summary()
    render_selected_state(selected_state)


def zoomToState(event):
    label = event.widget
    image = ui_state.get('map_photo')
    xLoc = event.x
    yLoc = event.y

    if image is not None:
        x_offset = max((label.winfo_width() - image.width()) // 2, 0)
        y_offset = max((label.winfo_height() - image.height()) // 2, 0)
        xLoc -= x_offset
        yLoc -= y_offset

    if image is not None and (xLoc < 0 or yLoc < 0 or xLoc >= image.width() or yLoc >= image.height()):
        return

    stateName = get_state_name_from_pixel(xLoc, yLoc)
    if stateName is None:
        messagebox.showerror('State Error', "That's not a state")
        return
    createNationalMap(stateName)

def getOnBallot(player, stateName, cost, window, event):
    global calendarOfContests
    global currentDate
    global states
    global players

    contestDate = None
    for state in calendarOfContests:
        if stateName == state[0]:
            contestDate = state[1]
            break

    currentOrg = states[stateName].organizations[player - 1]
    if currentOrg == 0 and contestDate is not None and currentDate > contestDate:
        messagebox.showerror('Timing Error', 'Too late to get on the ballot here')
        return
    if players[player].resources[1] - int(cost) < 0:
        if currentOrg <= 1:
            messagebox.showerror('Money Error', "You don't have enough money for that expansion")
        else:
            messagebox.showerror('Money Error', "You don't have enough money to further build your team here")
        return

    if currentOrg == 0:
        states[stateName].organizations[player - 1] = 1
    else:
        states[stateName].organizations[player - 1] += 1
    players[player].resources[1] = players[player].resources[1] - int(cost)
    try:
        players[player].addStat('org_money_total', int(cost))
        players[player].addStat('orgs_built', 1)
    except AttributeError:
        pass
    createNationalMap(stateName)


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
        messagebox.showerror('Money Error', "You don't have enough money for those ad buys")
        players[player].resources[1] -= allocatedMoney
        players[player].resources[0] -= allocatedTime
        return
    if totalTime > players[player].resources[0]:
        messagebox.showerror('Time Error', "You don't have enough time for all that campaigning")
        players[player].resources[1] -= allocatedMoney
        players[player].resources[0] -= allocatedTime
        return

    players[player].resources[1] -= totalAdCosts
    players[player].resources[0] -= totalTime
    currentState = states[stateName]
    for index, district in enumerate(currentState.districts):
        district.setAdsThisTurn(player - 1, addBuys[index].get())
        district.setCampaigningThisTurn(player - 1, campaingingTime[index].get())

    # Return to the national overview after saving the state's plan.
    createNationalMap()


def endTurn(window, fundraising):
    global player
    global numPlayers
    global currentDate
    global eventOfTheWeek
    global states
    global players
    global numTurns

    players[player].resources[0] -= fundraising
    fundraising += players[player].resources[0]
    calcEndTurn(fundraising)

    if player < numPlayers:
        player += 1
    else:
        calculateStateOpinions()
        currentDate += 1
        decideContests()
        player = 1
        eventOfTheWeek = random.randint(0, len(issueNames) - 1)
        _refresh_headline()
        for state in states:
            for district in states[state].districts:
                for person in players:
                    district.setCampaigningThisTurn(person - 1, 0)
                    district.setAdsThisTurn(person - 1, 0)

    if currentDate <= numTurns:
        autoSave()
        show_turn_transition_screen()
    else:
        show_final_results()


def next_player_button(top=None):
    start_active_turn_flow(True)


def save_and_quit():
    saveGame()
    exitGame()


def saveGame():
    root = init_app_root()
    file_path = filedialog.asksaveasfilename(parent=root, initialdir=os.path.join(os.getcwd(), 'CampaignSaves'), defaultextension='.save', filetypes=[('save games', '.save')])
    if not file_path:
        return
    saveGameSecond(file_path, None, False, True)


def saveGameSecond(fileName, window, autosave, direct_path=False):
    global player
    global currentDate
    global players
    global states
    global pastElections
    global weekResults
    global numTurns

    if window is not None:
        try:
            if window != app_window:
                window.destroy()
        except:
            pass

    saveFile = []
    saveFile.append(pickle.dumps(players))
    saveFile.append(pickle.dumps(states))
    saveFile.append(pickle.dumps(pastElections))
    saveFile.append(pickle.dumps(player))
    saveFile.append(pickle.dumps(currentDate))
    saveFile.append(pickle.dumps(weekResults))
    saveFile.append(pickle.dumps(numTurns))
    if direct_path:
        save_path = fileName
    else:
        save_path = os.path.join(os.getcwd(), 'CampaignSaves', fileName + '.save')
    pickle.dump(saveFile, open(save_path, 'wb'))
    if not autosave:
        messagebox.showinfo('Save Successful', 'Game saved successfully.')


def autoSave():
    autosaveFiles = ['autosave', 'autosave2', 'autosave3']
    filePaths = []
    for fileName in autosaveFiles:
        filePath = os.path.join(os.getcwd(), 'CampaignSaves', fileName + '.save')
        filePaths.append(filePath)
        if not os.path.isfile(filePath):
            saveGameSecond(fileName, None, True)
            return

    ages = []
    for fileName in filePaths:
        ages.append(os.stat(fileName).st_mtime)
    fileName = autosaveFiles[ages.index(min(ages))]
    saveGameSecond(fileName, None, True)


def syncRemoteSaves(silent=False):
    """Sync local CampaignSaves folder with the remote server."""
    config = RemoteSaveLoad.load_config()
    if not config.get('server_url') or not config.get('api_key'):
        if not silent:
            messagebox.showwarning('Sync Saves', 'Configure server URL and API key in remote_config.json first.')
        return
    save_dir = os.path.join(os.getcwd(), 'CampaignSaves')
    os.makedirs(save_dir, exist_ok=True)
    try:
        results = RemoteSaveLoad.sync_saves(config['server_url'], config['api_key'], save_dir)
        if not silent:
            messagebox.showinfo('Sync Saves',
                'Sync complete.\nUploaded: {}\nDownloaded: {}\nUp to date: {}'.format(
                    results['uploaded'], results['downloaded'], results['up_to_date']))
        return results
    except Exception as e:
        if not silent:
            messagebox.showerror('Sync Error', str(e))
        return None


def saveGameRemote():
    """Save locally, then upload that file to the remote server."""
    config = RemoteSaveLoad.load_config()
    if not config.get('server_url') or not config.get('api_key'):
        messagebox.showwarning('Remote Save', 'Configure server URL and API key in remote_config.json first.')
        return
    root = init_app_root()
    save_dir = os.path.join(os.getcwd(), 'CampaignSaves')
    os.makedirs(save_dir, exist_ok=True)
    file_path = filedialog.asksaveasfilename(parent=root, initialdir=save_dir,
                                             defaultextension='.save',
                                             filetypes=[('save games', '.save')])
    if not file_path:
        return
    saveGameSecond(file_path, None, True, True)
    try:
        with open(file_path, 'rb') as f:
            RemoteSaveLoad.upload_save(config['server_url'], config['api_key'],
                                       os.path.basename(file_path), f.read())
        messagebox.showinfo('Remote Save', 'Saved locally and uploaded to server.')
    except Exception as e:
        messagebox.showerror('Remote Save Error', str(e))


def loadGameRemote():
    """Pick a remote save, download it, and load it."""
    config = RemoteSaveLoad.load_config()
    if not config.get('server_url') or not config.get('api_key'):
        messagebox.showwarning('Remote Load', 'Configure server URL and API key in remote_config.json first.')
        return
    try:
        remote = RemoteSaveLoad.list_remote_saves(config['server_url'], config['api_key'])
    except Exception as e:
        messagebox.showerror('Remote Load Error', str(e))
        return
    if not remote:
        messagebox.showinfo('Remote Load', 'No remote saves found.')
        return

    root = init_app_root()
    picker = Toplevel(root)
    picker.title('Load from Server')
    picker.geometry('380x320')
    Label(picker, text='Select a remote save:').pack(anchor='w', padx=12, pady=(10, 4))
    lb = Listbox(picker)
    lb.pack(fill='both', expand=True, padx=12, pady=(0, 8))
    for s in remote:
        lb.insert(END, s['name'])

    def do_load():
        sel = lb.curselection()
        if not sel:
            return
        name = remote[sel[0]]['name']
        try:
            data = RemoteSaveLoad.download_save(config['server_url'], config['api_key'], name)
        except Exception as e:
            messagebox.showerror('Remote Load Error', str(e))
            return
        save_dir = os.path.join(os.getcwd(), 'CampaignSaves')
        os.makedirs(save_dir, exist_ok=True)
        local_path = os.path.join(save_dir, name)
        with open(local_path, 'wb') as f:
            f.write(data)
        picker.destroy()
        _loadFromPath(local_path)

    btns = Frame(picker)
    btns.pack(fill='x', padx=12, pady=(0, 12))
    Button(btns, text='Load', command=do_load).pack(side='left')
    Button(btns, text='Cancel', command=picker.destroy).pack(side='left', padx=8)


def _loadFromPath(file_path):
    global player, currentDate, players, states, pastElections, numPlayers, weekResults, numTurns
    try:
        saveFile = pickle.load(open(file_path, 'rb'))
    except (FileNotFoundError, pickle.UnpicklingError, TypeError) as e:
        messagebox.showerror('Load Error', 'Failed to load save file: {}'.format(str(e)))
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
    start_active_turn_flow(currentDate > 1)


def loadGame(window):
    global player
    global currentDate
    global players
    global states
    global pastElections
    global numPlayers
    global weekResults
    global numTurns

    root = init_app_root()
    file_path = filedialog.askopenfilename(parent=root, initialdir=os.path.join(os.getcwd(), 'CampaignSaves'), filetypes=[('save games', '.save')])
    if not file_path:
        mainMenu()
        return

    try:
        saveFile = pickle.load(open(file_path, 'rb'))
    except (FileNotFoundError, pickle.UnpicklingError, TypeError) as e:
        messagebox.showerror('Load Error', 'Failed to load save file: {}'.format(str(e)))
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
    start_active_turn_flow(currentDate > 1)


def show_final_results():
    winner = 0
    mostDelegates = 0
    for person in players:
        if players[person].delegateCount > mostDelegates:
            winner = person
            mostDelegates = players[person].delegateCount

    root, body = build_screen('Election Complete', 'Final standings, fundraising, and a per-candidate breakdown of how the campaign played out.')

    # Scrollable container so the report can grow without overflowing.
    outer = Frame(body, bg='#f3efe2')
    outer.pack(fill='both', expand=True)
    canvas = Canvas(outer, bg='#f3efe2', highlightthickness=0)
    scroll = Scrollbar(outer, orient='vertical', command=canvas.yview)
    inner = Frame(canvas, bg='#f3efe2')
    inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.create_window((0, 0), window=inner, anchor='nw')
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    canvas.bind('<Enter>', lambda e: _bound_to_mousewheel(e, canvas))
    canvas.bind('<Leave>', lambda e: _unbound_to_mousewheel(e, canvas))

    winner_card = make_card(inner, 'Winner')
    winner_card.pack(fill='x', pady=(0, 16))
    Label(winner_card,
          text='{} wins with {} delegates after {} weeks.'.format(
              players[winner].publicName, mostDelegates, currentDate - 1),
          bg='white', justify=LEFT, wraplength=900,
          font=('TkDefaultFont', 12, 'bold')).pack(anchor='w', padx=12, pady=(0, 12))

    # Final standings table.
    standings = make_card(inner, 'Final Standings')
    standings.pack(fill='x', pady=(0, 16))
    sorted_players = sorted(players.values(), key=lambda p: p.delegateCount, reverse=True)
    header = Frame(standings, bg='white')
    header.pack(fill='x', padx=12, pady=(0, 4))
    for col, w in [('Rank', 6), ('Candidate', 22), ('Delegates', 11), ('States', 8), ('Districts', 10)]:
        Label(header, text=col, bg='white', font=('TkDefaultFont', 9, 'bold'), width=w, anchor='w').pack(side='left')
    for rank, p in enumerate(sorted_players, 1):
        row = Frame(standings, bg='white')
        row.pack(fill='x', padx=12, pady=1)
        states_won = p.getStat('states_won', []) if hasattr(p, 'getStat') else []
        Label(row, text=str(rank), bg='white', width=6, anchor='w').pack(side='left')
        Label(row, text=p.publicName, bg='white', width=22, anchor='w').pack(side='left')
        Label(row, text=str(p.delegateCount), bg='white', width=11, anchor='w').pack(side='left')
        Label(row, text=str(len(states_won)), bg='white', width=8, anchor='w').pack(side='left')
        Label(row, text=str(p.getStat('districts_won', 0) if hasattr(p, 'getStat') else 0),
              bg='white', width=10, anchor='w').pack(side='left')

    # Per-candidate detail cards.
    for p in sorted_players:
        get = p.getStat if hasattr(p, 'getStat') else (lambda k, d=0: d)
        card = make_card(inner, '{} ({})'.format(p.publicName, p.isHuman))
        card.pack(fill='x', pady=(0, 12))

        # Money summary.
        fund_inc = get('fundraising_income_total', 0)
        local_inc = get('local_income_total', 0)
        total_inc = fund_inc + local_inc
        ad_spent = get('ad_money_total', 0)
        org_spent = get('org_money_total', 0)
        time_camp = get('campaigning_hours_total', 0)
        time_fund = get('fundraising_hours_total', 0)
        money_lines = [
            'Total raised: ${:,}'.format(int(total_inc)),
            '   Fundraising-time income: ${:,}  ({} hours of fundraising)'.format(int(fund_inc), int(time_fund)),
            '   Local fundraising income: ${:,}'.format(int(local_inc)),
            'Spent on ads: ${:,}'.format(int(ad_spent)),
            'Spent on organization: ${:,}  ({} org tiers built)'.format(int(org_spent), int(get('orgs_built', 0))),
            'Campaigning time used: {} hours'.format(int(time_camp)),
            'Final cash on hand: ${:,}'.format(int(p.resources[1])),
            'Final momentum: {:.1f}'.format(p.momentum),
        ]
        for line in money_lines:
            Label(card, text=line, bg='white', justify=LEFT, wraplength=900).pack(anchor='w', padx=12, pady=1)

        # Support breakdown.
        sup_org = get('support_from_org', 0.0)
        sup_camp = get('support_from_campaign', 0.0)
        sup_ads = get('support_from_ads', 0.0)
        sup_total = sup_org + sup_camp + sup_ads or 1.0
        Label(card, text='Where their support came from:',
              bg='white', font=('TkDefaultFont', 10, 'bold'), justify=LEFT).pack(anchor='w', padx=12, pady=(8, 2))
        for source_name, value in [
            ('Organization', sup_org),
            ('Campaigning time', sup_camp),
            ('Ad buys', sup_ads),
        ]:
            pct = 100.0 * value / sup_total
            Label(card,
                  text='   {}: {:.0f} support points  ({:.1f}%)'.format(source_name, value, pct),
                  bg='white', justify=LEFT).pack(anchor='w', padx=12, pady=1)

        # Efficiency: support per hour campaigning, per dollar of ads, per dollar org.
        eff_lines = []
        if time_camp > 0:
            eff_lines.append('   Support per campaign hour: {:.1f}'.format(sup_camp / time_camp))
        if ad_spent > 0:
            eff_lines.append('   Support per $1k of ads: {:.2f}'.format(sup_ads / (ad_spent / 1000.0)))
        if org_spent > 0:
            eff_lines.append('   Support per $1k of org: {:.2f}'.format(sup_org / (org_spent / 1000.0)))
        if eff_lines:
            Label(card, text='Efficiency:', bg='white', font=('TkDefaultFont', 10, 'bold'), justify=LEFT).pack(anchor='w', padx=12, pady=(8, 2))
            for line in eff_lines:
                Label(card, text=line, bg='white', justify=LEFT).pack(anchor='w', padx=12, pady=1)

        # States won.
        states_won = get('states_won', [])
        if states_won:
            Label(card, text='States won ({}):'.format(len(states_won)),
                  bg='white', font=('TkDefaultFont', 10, 'bold'), justify=LEFT).pack(anchor='w', padx=12, pady=(8, 2))
            Label(card, text=', '.join(states_won), bg='white', justify=LEFT, wraplength=880).pack(anchor='w', padx=12, pady=(0, 4))
        else:
            Label(card, text='No state wins.', bg='white', justify=LEFT).pack(anchor='w', padx=12, pady=(8, 2))

    actions = Frame(inner, bg='#f3efe2')
    actions.pack(anchor='w', pady=(0, 8))
    Button(actions, text='Return to Main Menu', command=mainMenu, padx=14).pack(side='left')
    Button(actions, text='Exit Game', command=exitGame, padx=14).pack(side='left', padx=8)


def exitGame():
    close_modal()
    global app_window
    if app_window is not None and app_window.winfo_exists():
        app_window.destroy()
    if app_root is not None and app_root.winfo_exists():
        app_root.destroy()
    sys.exit()


main()



