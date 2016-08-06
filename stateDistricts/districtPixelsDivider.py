import os

def main():
    districtPixels = open('districtList.txt' , 'r')
    currentState = ''
    for line in districtPixels:
        l = line.split(',')
        stateName = l[2]
        if stateName == currentState:
            stateOut.write(line)

        else:
            stateOut = open(stateName+ '.txt', 'w')
            stateOut.write(line)
            currentState = stateName



main()