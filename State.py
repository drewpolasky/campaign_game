class State:
    def __init__(self, stateName, positions):
        self.name = stateName
        self.positions = positions
        self.opinions = []
        self.support = []
        self.organizations = []
        self.districts = []
        self.pollingAverage = []

    def updateSupport(self, numPlayers,calendarOfContests, currentDate):        
        newSupport = []
        for j in range(numPlayers):
            newSupport.append(0)
        for i in range(numPlayers): 
            for district in self.districts:
                newSupport[i] += district.support[i] * district.population
        self.support = newSupport
        self.calculatePollingAverage(calendarOfContests, currentDate)
        return

    def calculatePollingAverage(self, calendarOfContests, currentDate):
        for election in calendarOfContests:
            if election[0] == self.name:
                electionDate = election[1]
        numDecided = 0
        timeToElection = electionDate - currentDate
        stateVoteTotals = []
        for i in range(len(self.support)):
            stateVoteTotals.append(0)
        if timeToElection >= 0:
            for district in self.districts:
                polling = []
                for person in range(len(self.support)):
                    totalSupport = float(sum(district.support))
                    numDecided = 1 - (2.5 + self.organizations[person] / 80.0) ** (totalSupport / -100.0)
                    numVoting = numDecided * district.population * 150000
                    
                    numVoters = (district.support[person] / (totalSupport + 0.0001)) * numVoting
                    stateVoteTotals[person] += numVoters
                    polling.append(round(numVoters / (district.population * 150000.0) * 100, 1))
                district.pollingAverage = polling

            totalVotes = float(sum(stateVoteTotals))
            statePolling = []
            for person in range(len(stateVoteTotals)):
                statePolling.append(round(stateVoteTotals[person]/ (totalVotes + 1) * 100 , 1))
            self.pollingAverage = statePolling
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
        self.positions = []
        self.support = []
        self.pollingAverage = []
        self.campaigningThisTurn = []
        self.adsThisTurn = []

    def setSupport(self, playerIndex, s):
        try:
            self.support[playerIndex] += s
        except IndexError:
            self.support.append(s)

    def setPositions(self, opinionList):
        self.positions = opinionList

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