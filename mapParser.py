#the goal here is to take in each pixel of the national map and sort it into which state its in, then create a list that can be used by the main program
#for the mouse listener.
import sys
from PIL import Image
import Tkinter

def main():
    mapImage = Image.open("nationalMap.png")
    mapPix = mapImage.load()
    imageWidth = mapImage.size[0]
    imageHeight = mapImage.size[1]
    print imageHeight
    lastValue = [0,0,0]
    for y in range(imageHeight):
        for x in range(imageWidth):
            mapPix[x,y] = 1 


            '''currentValue = mapPix[x,y]
            if currentValue != lastValue:
                print currentValue, x, y
            lastValue = currentValue'''
    mapImage.show()



main()