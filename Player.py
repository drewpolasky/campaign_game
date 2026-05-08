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
        self.aiStrategy = 'Default'   # Picked at setup when controller is AI.
        # Cumulative campaign stats for the end-of-game report. New attributes
        # are read defensively so old saves still load (use _stat() helper).
        self.stats = {
            'states_won': [],
            'districts_won': 0,
            'fundraising_hours_total': 0,
            'campaigning_hours_total': 0,
            'ad_money_total': 0,
            'org_money_total': 0,
            'fundraising_income_total': 0,
            'local_income_total': 0,
            'support_from_org': 0.0,
            'support_from_campaign': 0.0,
            'support_from_ads': 0.0,
            'orgs_built': 0,
            'turns_played': 0,
        }

    def _ensure_stats(self):
        if not hasattr(self, 'stats') or self.stats is None:
            self.stats = {}
        defaults = {
            'states_won': [],
            'districts_won': 0,
            'fundraising_hours_total': 0,
            'campaigning_hours_total': 0,
            'ad_money_total': 0,
            'org_money_total': 0,
            'fundraising_income_total': 0,
            'local_income_total': 0,
            'support_from_org': 0.0,
            'support_from_campaign': 0.0,
            'support_from_ads': 0.0,
            'orgs_built': 0,
            'turns_played': 0,
        }
        for k, v in defaults.items():
            self.stats.setdefault(k, v)

    def addStat(self, key, amount):
        self._ensure_stats()
        if key in ('states_won',):
            self.stats[key].append(amount)
        else:
            self.stats[key] = self.stats.get(key, 0) + amount

    def getStat(self, key, default=0):
        self._ensure_stats()
        return self.stats.get(key, default)

    def setPositions(self, positions):
        self.positions = positions

    def endTurn(self, turn, fundraisingIncome, localIncome,
                fundraisingHours=0, campaigningHours=0, adSpend=0):
        self._ensure_stats()
        self.history[turn] = {}
        self.history[turn]['fundraisingIncome'] = fundraisingIncome
        localIncome = round(localIncome)
        self.history[turn]['localIncome'] = localIncome
        self.history[turn]['fundraisingHours'] = fundraisingHours
        self.history[turn]['campaigningHours'] = campaigningHours
        self.history[turn]['adSpend'] = adSpend
        self.stats['fundraising_income_total'] += fundraisingIncome
        self.stats['local_income_total'] += localIncome
        self.stats['fundraising_hours_total'] += fundraisingHours
        self.stats['campaigning_hours_total'] += campaigningHours
        self.stats['ad_money_total'] += adSpend
        self.stats['turns_played'] += 1

    def setName(self, name):
        self.publicName = name

    def setHuman(self, isHuman):
        self.isHuman = isHuman
