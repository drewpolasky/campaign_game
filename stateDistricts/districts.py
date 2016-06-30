

def main():
    districtList = open('districtList.txt', 'r')
    districts = open('districts.txt', 'w')
    stateName = ''
    districtName = ''
    for line in districtList:
        l = line.split(',')
        if stateName == l[2]:
            if districtName != l[3]:
                districts.write('%s, %s' %(l[2],l[3]))
                districtName =l[3]
        else:
            stateName = l[2]
            districtName = l[3]
            districts.write('%s, %s' %(l[2],l[3]))





main()