#side program to initialize states and districts. Shouldn't be needed in the main game at all. 
#splits larger map into districts clicked on by the user, and takes user input on their name. 

from Tkinter import *
import tkMessageBox
from PIL import Image, ImageTk
import os

def main():
    window = Tk()
    mapWindow = PanedWindow()

    natMapImage = Image.open('nationalMap.jpg')
    natMapImg = ImageTk.PhotoImage(natMapImage)

    state = Label(window, image = natMapImg)
    mapWindow.add(state)

    mapWindow.pack()
    state.bind('<Button-1>' , defineState)
    window.mainloop()
    '''for i in os.listdir(os.getcwd()):
        if i.endswith(".jpeg"):
            print i
            window = Tk()
            mapWindow = PanedWindow()

            natMapImage = Image.open(i)
            natMapImg = ImageTk.PhotoImage(natMapImage)

            state = Label(window, image = natMapImg)
            mapWindow.add(state)

            mapWindow.pack()
            state.bind('<Button-1>' , defineState)
            window.mainloop()'''

'''def returnColor(event):
    natMap = event.widget

    natMapImage = Image.open("New York.jpeg")
    mapPix = natMapImage.load()

    print mapPix[event.x, event.y]'''

#this only was used for game set up (creating the pixel list). It won't be used in normal game function.
def defineDistrict(event):     #when a state is clicked on all this should find all the pixels contigous(no black lines) to the one clicked, then prompt for the state's name, and create a database assigning each pixel to a state. 
    districtList = open('districtList.txt' , 'a')

    for i in os.listdir(os.getcwd()):
        if i.endswith(".jpeg"):
            stateMap = event.widget
            mapPix = stateMap.load()

            initPoint = (event.x, event.y)
            allPoints = [initPoint]
            endPoints = []      #because its the list of points we should have at the end, not the points that are ends
            while len(allPoints) > 0:
                for point in allPoints:
                    newLeft = (point[0] - 1, point[1])
                    newRight = (point[0] + 1, point[1])
                    newUp = (point[0], point[1] - 1)
                    newDown = (point[0], point[1] + 1)
                    allPoints.remove(point)
                    endPoints.append(point)
                    if newLeft not in allPoints and mapPix[newLeft] > (200, 200, 200) and newLeft not in endPoints:
                        allPoints.append(newLeft)
                        mapPix[newLeft] = 0
                    if newRight not in allPoints and mapPix[newRight] > (200, 200, 200) and newRight not in endPoints:
                        allPoints.append(newRight)
                        mapPix[newRight] = 0
                    if newUp not in allPoints and mapPix[newUp] > (200, 200, 200) and newUp not in endPoints:
                        allPoints.append(newUp)
                        mapPix[newUp] = 0
                    if newDown not in allPoints and mapPix[newDown] > (200, 200, 200) and newDown not in endPoints:
                        allPoints.append(newDown)
                        mapPix[newDown] = 0
            natMapImage.show()
                
            '''stateName = raw_input("what state")
            for point in endPoints:
                pixelList.write('%s,%s,%s \n' %(point[0], point[1], stateName))'''

def defineState(event):     #when a state is clicked on all this should find all the pixels contigous(no black lines) to the one clicked, then prompt for the state's name, and create a database assigning each pixel to a state. 
    pixelList = open('pixelList.txt' , 'a')
    natMapImage = Image.open("nationalMap.jpg")
    mapPix = natMapImage.load()
    print mapPix[event.x, event.y]
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
            if newLeft not in allPoints and mapPix[newLeft][0] > 205 and newLeft not in endPoints:
                allPoints.append(newLeft)
                mapPix[newLeft] = 0
            if newRight not in allPoints and mapPix[newRight][0] > 205 and newRight not in endPoints:
                allPoints.append(newRight)
                mapPix[newRight] = 0
            if newUp not in allPoints and mapPix[newUp][0] > 205 and newUp not in endPoints:
                allPoints.append(newUp)
                mapPix[newUp] = 0
            if newDown not in allPoints and mapPix[newDown][0] > 205     and newDown not in endPoints:
                allPoints.append(newDown)
                mapPix[newDown] = 0
    natMapImage.show()
    
    stateName = raw_input("what state")
    for point in endPoints:
        pixelList.write('%s,%s,%s \n' %(point[0], point[1], stateName))


main()