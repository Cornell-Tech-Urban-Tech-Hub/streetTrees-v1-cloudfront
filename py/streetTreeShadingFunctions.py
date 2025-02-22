#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 24 08:07:59 2022

@author: joe
"""

#

#required dependencies

import laspy
import numpy as np
import pandas as pd
import json
from pyproj import Transformer
import math
from scipy.spatial import ConvexHull, convex_hull_plot_2d
import matplotlib.pyplot as plt
import matplotlib.path as mpltPath
import datetime
from multiprocessing import Pool

#

def processLas(lasFileName):
    if lasFileName.endswith('.las'):
        las = laspy.read(lasFileName)
        #point_format = las.point_format
        lidar_points = np.array((las.X,las.Y,las.Z,las.intensity,las.classification, las.return_number, las.number_of_returns)).transpose()
        lidar_df = pd.DataFrame(lidar_points)
        lidar_df[0] = lidar_df[0]/100
        lidar_df[1] = lidar_df[1]/100
        lidar_df[2] = lidar_df[2]/100
        lidar_df.columns = ['X', 'Y', 'Z', 'intens', 'class', 'return_number', 'number_of_returns']
    else:
        print('not a las file')
    return lidar_df

#

def lasDFcanopy(lidar_df):
    lidar_canopy_df = lidar_df[( lidar_df['number_of_returns'] - lidar_df['return_number'] ) > 0 ]
    return lidar_canopy_df

#

def lasDFclip(lidar_df,xMin,xMax,yMin,yMax):
    lidar_clip_df = lidar_df[ lidar_df['X'] >= xMin ]
    lidar_clip_df = lidar_clip_df[ lidar_clip_df['X'] <= xMax ]
    lidar_clip_df = lidar_clip_df[ lidar_clip_df['Y'] >= yMin ]
    lidar_clip_df = lidar_clip_df[ lidar_clip_df['Y'] <= yMax ]
    return lidar_clip_df

#

def treeDFclip(tree_df,xMin,xMax,yMin,yMax):
    tree_clip_df = tree_df[ tree_df['x_sp'] >= xMin ]
    tree_clip_df = tree_clip_df[ tree_clip_df['x_sp'] <= xMax ]
    tree_clip_df = tree_clip_df[ tree_clip_df['y_sp'] >= yMin ]
    tree_clip_df = tree_clip_df[ tree_clip_df['y_sp'] <= yMax ]
    #add a Z clip
    return tree_clip_df

#

def readGeoJSON(filepath):
    with open(filepath) as f:
        features = json.load(f)["features"]                
    return features

#

def footprintPointsFromGeoJSON(feature):   
    points = []
    height = feature["properties"]["heightroof"] ################## verify this is the correct attribute name
    for polygonPart in feature["geometry"]["coordinates"]:
        for polygonSubPart in polygonPart:
            for coordinates in polygonSubPart:
                point = [coordinates[0],coordinates[1],height]
                points.append(point)                  
    return points, height

#

def convertCoords(x,y):
    transformer = Transformer.from_crs("epsg:2263", "epsg:4326")
    lat, lon = transformer.transform(x, y)
    return lat, lon

#

def convertLatLon(lat,lon):
    #translate from geojson CRS (NAD 1983) to .las CRS (UTM Zone 18N (meters))
    transformer = Transformer.from_crs( "epsg:4326", "epsg:2263" ) 
    x, y = transformer.transform(lat, lon)
    return x, y

#

def projectToGround(point,az,amp):
    if type(point[2]) is float:
        sinAz = math.sin( math.radians( az + 180.0 ) )
        cosAz = math.cos( math.radians( az + 180.0 ) )
        tanAmp = math.tan( math.radians(amp) )
        pointGroundX = point[0] + ( ( point[2] / tanAmp ) *sinAz )
        pointGroundY = point[1] + ( ( point[2] / tanAmp ) *cosAz )
        pointGroundZ =  point[2] * 0
        return pointGroundX,pointGroundY,pointGroundZ
    else: 
        print('bad Z')
        return point[0],point[1],1.0

#

def projectToGroundX(point,az,amp):
    sinAz = math.sin( math.radians( az + 180.0 ) )
    cosAz = math.cos( math.radians( az + 180.0 ) )
    tanAmp = math.tan( math.radians(amp) )
    pointGroundX = point[0] + ( ( point[2] / tanAmp ) * sinAz )   
    return pointGroundX


#

def projectToGroundY(point,az,amp):   
    sinAz = math.sin( math.radians( az + 180.0 ) )
    cosAz = math.cos( math.radians( az + 180.0 ) )
    tanAmp = math.tan( math.radians(amp) )
    pointGroundY = point[1] + ( ( point[2] / tanAmp ) * cosAz )
    return pointGroundY


#

def pointsForHull(points,az,amp):
    groundPointList = []
    for point in points:
        point[0],point[1] = convertLatLon(point[1],point[0])
        groundPointList.append([point[0],point[1]])
        groundPoint = projectToGround(point,az,amp)
        groundPointList.append([groundPoint[0],groundPoint[1]])    
    return groundPointList

#

def pointsForBufferedHull(points):
    groundPointList = []
    for point in points:
        #print(point)
        #point[0],point[1] = convertLatLon(point[1],point[0])
        #print(point)
        groundPointList.append([point[0],point[1]])   
    return groundPointList

#

def convexHull2D(points):
    points = np.array(points)
    hull = ConvexHull(points)
    return hull

#

def inBuilding(points, hull):      
    vertexList = (hull.vertices).tolist()
    polygonPoints = []
    for index in vertexList:
        polygonPoints.append(hull.points[index])
    path = mpltPath.Path(polygonPoints)
    pointsIn = points[['X','Y']]
    points['temp'] = path.contains_points(pointsIn) 
    points['inBuilding'] = np.where( (points['inBuilding'] == 1) | (points['temp'] == 1),1,0 )
    return points

#

def inShadow(points, hull):    
    vertexList = (hull.vertices).tolist()
    polygonPoints = []
    for index in vertexList:
        polygonPoints.append(hull.points[index])
    path = mpltPath.Path(polygonPoints)
    pointsIn = points[['X','Y']]
    pointsInGround = points[['groundX','groundY']]
    points['temp'] = path.contains_points(pointsIn) * path.contains_points(pointsInGround)
    points['inShade'] = np.where( (points['inShade'] == 1) | (points['temp'] == 1),1,0 )
    return points

#

def inFacade(points, hull):
    vertexList = (hull.vertices).tolist()
    polygonPoints = []
    for index in vertexList:
        polygonPoints.append(hull.points[index])
    path = mpltPath.Path(polygonPoints)
    pointsIn = points[['groundX','groundY']]
    points['temp'] = path.contains_points(pointsIn)
    points['inFacade'] = np.where( (points['inFacade'] == 1) | (points['temp'] == 1),1,0 )
    return points        


#

def trimGeoJSON(features,xMin,xMax,yMin,yMax,latLon):
    
    features2 = []
    
    for feature in features[:]:
        buildingPoints,buildingHeight = footprintPointsFromGeoJSON(feature)
        xs = []
        ys = []
        for buildingPoint in buildingPoints:
            xs.append(buildingPoint[0])
            ys.append(buildingPoint[1])
        xCenter = sum(xs)/len(xs)
        yCenter = sum(ys)/len(ys)
        
        if latLon == 'latLon':
            xCenter,yCenter = convertLatLon(yCenter,xCenter)
        else:
            xCenter,yCenter = xCenter,yCenter
        
        if xCenter > xMin and xCenter < xMax and yCenter > yMin and yCenter < yMax:
            features2.append(feature)
        else:
            continue
        
    return features2


#

def removeBuildingsFromLas(buildingsBufferedPaath,lasdf):
    #buffered buildings currently use state plane coordinates for their vertices 
    featuresBuffered = readGeoJSON(buildingsBufferedPaath)

    for feature in featuresBuffered:
        buildingPoints,buildingHeight = footprintPointsFromGeoJSON(feature)
        buildingPoints = pointsForBufferedHull(buildingPoints)
        buildingHull = convexHull2D(buildingPoints)
        lasdf = inBuilding(lasdf,buildingHull)
        
    lasBuildings = lasdf[lasdf['inBuilding'] == 1]
    lasdf = lasdf[lasdf['inBuilding'] == 0]
    
    return lasBuildings, lasdf
    

#

def lasPreprocess(lasTileNumber):
    lasdf = processLas('las/{}.las'.format(lasTileNumber))
    lasdf = lasdf.dropna()

    groundElevation = lasdf[lasdf['class']==2]['Z'].mean()

    lasdf = lasDFcanopy(lasdf)

    lasdf['Z'] = lasdf['Z'] - groundElevation

    lasdf = lasdf[ lasdf['Z'] < 1000 ]

    lasdf['temp'] = 0
    lasdf['inBuilding'] = 0
        
    lasBuildings, lasdf =  removeBuildingsFromLas('buildings/buildingsTile{}buffered.geojson'.format(lasTileNumber),lasdf)
    
    return lasBuildings, lasdf

def lasProcess(iterator):
    #az here is geometric degrees (counterclockwise, north = 90) not compass heading degrees (clockwise, north = 0)
    lasdf = iterator[0]
    lasTileNumber = iterator[1]
    az = iterator[2]
    amp = iterator[3]
    
    lasdf['groundX'] = lasdf.apply(lambda x: projectToGroundX([x['X'],x['Y'],x['Z']],az,amp) , axis=1)
    lasdf['groundY'] = lasdf.apply(lambda x: projectToGroundY([x['X'],x['Y'],x['Z']],az,amp) , axis=1)

    lasdf['temp'] = 0
    lasdf['inShade'] = 0

    features = readGeoJSON('buildings/buildingsTile{}.geojson'.format(lasTileNumber))

    hulls = []

    #check in shadow
    for feature in features:
        buildingPoints,buildingHeight = footprintPointsFromGeoJSON(feature)
        buildingPointsGround = pointsForHull(buildingPoints,az,amp)
        buildingHull = convexHull2D(buildingPointsGround)
        hulls.append(buildingHull)
        lasdf = inShadow(lasdf,buildingHull)

    lasInShade = lasdf[lasdf['inShade'] == 1]
    lasNotShade = lasdf[lasdf['inShade'] == 0]

    lasNotShade['temp'] = 0
    lasNotShade['inFacade'] = 0

    #check shading facade
    for buildingHull in hulls:
        lasNotShade = inFacade(lasNotShade,buildingHull)

    lasShadeFacade = lasNotShade[lasNotShade['inFacade'] == 1]
    lasShadeRoad = lasNotShade[lasNotShade['inFacade'] == 0]

    print('las shading road')
    print(lasShadeRoad)
    print('las in shade')
    print(lasInShade)
    print('las shading facade')
    print(lasShadeFacade)
    
    lasShadeRoad.to_csv('shadeShadingShadedDataframes/{}_{}_{}_shadingGround.csv'.format(lasTileNumber,az,amp))
    lasInShade.to_csv('shadeShadingShadedDataframes/{}_{}_{}_inShade.csv'.format(lasTileNumber,az,amp))
    lasShadeFacade.to_csv('shadeShadingShadedDataframes/{}_{}_{}_shadingFacade.csv'.format(lasTileNumber,az,amp))


############################################################################################################################################################################



startTime = str(datetime.datetime.now())


#


lasdf25252buildingPoints,lasdf25252 = lasPreprocess('25252')
#lasdf32187buildingPoints,lasdf32187 = lasPreprocess('32187')
#lasdf987180buildingPoints,lasdf987180 = lasPreprocess('987180')

print('Preprocessing done')

#

iterators = [
    #[lasdf25252,'25252',90,38], #Summer Solstice: 2022 06 21, 0800
    #[lasdf25252,'25252',101,49],  #Summer Solstice: 2022 06 21, 0900
    #[lasdf25252,'25252',116,60],  #Summer Solstice: 2022 06 21, 1000
    [lasdf25252,'25252',140,69],  #Summer Solstice: 2022 06 21, 1100
    [lasdf25252,'25252',182,73],  #Summer Solstice: 2022 06 21, 1200
    [lasdf25252,'25252',222,68]#,  #Summer Solstice: 2022 06 21, 1300
    #[lasdf25252,'25252',245,59],  #Summer Solstice: 2022 06 21, 1400
    #[lasdf25252,'25252',260,48],  #Summer Solstice: 2022 06 21, 1500
    #[lasdf25252,'25252',270,37]  #Summer Solstice: 2022 06 21, 1600
    ]


if __name__ == '__main__':
    with Pool() as p:
        p.map(lasProcess, iterators)



print('Started processing at ' + startTime)
endTime = str(datetime.datetime.now())
print('Finished processing at ' + endTime)




# #############################################################

# #3d plot 

# treeLat = 40.68449261
# treeLon = -73.98669463

# treeX, treeY = convertLatLon(treeLat,treeLon)

# plt.clf()
# plt.close()

# import matplotlib.path as mpltPath
# import matplotlib as mpl
# from mpl_toolkits.mplot3d import Axes3D

# fig = plt.figure(figsize=(3,3), dpi=600, constrained_layout=True)

# ax1 = fig.add_subplot(1, 1, 1, projection='3d') ############

# canopy_radius = 25

# lasBuildings['X'] = lasBuildings['X'] - treeX
# lasBuildings['Y'] = lasBuildings['Y'] - treeY
# lasBuildings = lasBuildings[ ( ( (lasBuildings['X'] )**2 + ( lasBuildings['Y'] )**2 ) ** 0.5 ) < canopy_radius*3 ]

# lasShadeRoad['X'] = lasShadeRoad['X'] - treeX
# lasShadeRoad['Y'] = lasShadeRoad['Y'] - treeY
# lasShadeRoad = lasShadeRoad[ ( ( ( lasShadeRoad['X'] )**2 + ( lasShadeRoad['Y'] )**2 ) ** 0.5 ) < canopy_radius ]


# lasInShade['X'] = lasInShade['X'] - treeX
# lasInShade['Y'] = lasInShade['Y'] - treeY
# lasInShade = lasInShade[ ( ( ( lasInShade['X'] )**2 + ( lasInShade['Y'] )**2 ) ** 0.5 ) < canopy_radius ]

# lasShadeFacade['X'] = lasShadeFacade['X'] - treeX
# lasShadeFacade['Y'] = lasShadeFacade['Y'] - treeY
# lasShadeFacade = lasShadeFacade[ ( ( ( lasShadeFacade['X'] )**2 + ( lasShadeFacade['Y'] )**2 ) ** 0.5 ) < canopy_radius ]

# xs = []
# ys = []
# zs = []

# for x in range(-canopy_radius,canopy_radius+1):
#     for y in range(-canopy_radius,canopy_radius+1):
#         xs.append(x)
#         ys.append(y)
#         zs.append(0.1)
#         xs.append(x)
#         ys.append(y)
#         zs.append(canopy_radius*2)

# ax1.scatter3D(xs, ys, zs, color='whitesmoke', zdir='z', s=0.01, marker='+', depthshade=True)
# #ax1.scatter3D(lasBuildings['X'], lasBuildings['Y'], lasBuildings['Z'], color='lightgray', zdir='z', s=0.01, marker='o', depthshade=True)
# ax1.scatter3D(lasShadeRoad['X'], lasShadeRoad['Y'], lasShadeRoad['Z'],color='seagreen', zdir='z', s=0.02, marker='o', depthshade=True)
# ax1.scatter3D(lasInShade['X'], lasInShade['Y'], lasInShade['Z'],color='black', zdir='z', s=0.02,marker='o', depthshade=True)
# ax1.scatter3D(lasShadeFacade['X'], lasShadeFacade['Y'], lasShadeFacade['Z'],color='indianred', zdir='z', s=0.02, marker='o', depthshade=True)


# ax1.view_init(90, 0)

# ax1.set_xticks([])
# ax1.set_yticks([])
# ax1.set_zticks([])
# #ax1.grid(False)
# ax1.set_axis_off()

# ax1.xaxis.set_pane_color((1.0, 1.0, 1.0, 0.0))
# ax1.yaxis.set_pane_color((1.0, 1.0, 1.0, 0.0))
# ax1.zaxis.set_pane_color((1.0, 1.0, 1.0, 0.0))

# ax1.set_xlim3d(-canopy_radius, canopy_radius)
# ax1.set_ylim3d(-canopy_radius, canopy_radius)
# ax1.set_zlim3d(0, canopy_radius*2)

# #fig.subplots_adjust(bottom=-0.1, top=1.1, left=-0.1, right=1.1, wspace=-0.1, hspace=-0.1)

# fig.savefig('3dtree.png')

# plt.show()

# #plt.close()













