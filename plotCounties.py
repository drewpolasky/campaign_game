#playing around with cartopy to show county level things

import numpy
import cartopy
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.shapereader as shpreader
import matplotlib.pyplot as plt


#class countyMap()
	
	#def __init__(self):

def show_map():
	#reader = shpreader.Reader('shapefiles/countyp020.shp')
	reader = shpreader.Reader('shapefiles/cgd114p010g.shp')
	counties = list(reader.geometries())

	COUNTIES = cfeature.ShapelyFeature(counties, ccrs.PlateCarree())

	plt.figure(figsize=(20, 12))
	ax = plt.axes(projection=ccrs.PlateCarree())

	ax.add_feature(cfeature.LAND.with_scale('50m'))
	ax.add_feature(cfeature.OCEAN.with_scale('50m'))
	ax.add_feature(cfeature.LAKES.with_scale('50m'))
	ax.add_feature(cfeature.STATES.with_scale('50m'))
	ax.add_feature(COUNTIES, facecolor='none', edgecolor='gray')

	ax.coastlines('50m')

	ax.set_extent([-125, -65, 25, 47])
	plt.show()

if __name__ == '__main__':
	show_map()