class Player:
    def __init__(self, player):
        self.name = player
        self.isHuman = 'human'       #not a boolean
        self.publicName = ''
        self.resources = [80, 100000]
        self.positions = []
        self.delegateCount = 0
        self.momentum = 0
        self.history = {}

    def setPositions(self, positions):
        self.positions = positions

    def endTurn(self, turn, fundraisingIncome, localIncome): #, spending):
        self.history[turn] = {}
        self.history[turn]['fundraisingIncome'] = fundraisingIncome
        localIncome = round(localIncome)
        self.history[turn]['localIncome'] = localIncome
        #history[endTurn]['spending'] = spending

    def setName(self, name):
        self.publicName = name

    def setHuman(self, isHuman):
        self.isHuman = isHuman
