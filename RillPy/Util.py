#! /usr/bin/env python
#coding=utf-8
from osgeo import gdal
from osgeo import osr
import os,sys
import arcpy
import numpy
from arcpy import env

sys.setrecursionlimit(1000000) ## to avoid the error: maximum recursion depth exceeded in cmp
##  Const Variables Definition  ##
DIR_ITEMS = {1:(0,1),
             2:(1,1),
             4:(1,0),
             8:(1,-1),
             16:(0,-1),
             32:(-1,-1),
             64:(-1,0),
             128:(-1,1)}
DIR_VALUES = [1,2,4,8,16,32,64,128]
MINI_VALUE = 0.000001
LEFT_DELATA = {2:(1,0),
               8:(0,-1),
               32:(-1,0),
               128:(0,1),
               1:(0,0),
               4:(0,0),
               16:(0,0),
               64:(0,0)}
RIGHT_DELATA = {2:(0,1),
               8:(1,0),
               32:(0,-1),
               128:(-1,0),
               1:(0,0),
               4:(0,0),
               16:(0,0),
               64:(0,0)}

##  End Const Variables Definition  ##

##  Define Utility Functions  ##
def downstream_index(DIR_VALUE, i, j):
    drow, dcol = DIR_ITEMS[DIR_VALUE]
    return i+drow, j+dcol

class Raster:
    def __init__(self, nRows, nCols, data, noDataValue=None, geotransform=None, srs=None):
        self.nRows = nRows
        self.nCols = nCols
        self.data = data
        self.noDataValue = noDataValue
        self.geotrans = geotransform
        self.srs = srs
        self.dx = geotransform[1]
        self.xMin = geotransform[0]
        self.xMax = geotransform[0] + nCols*geotransform[1]
        self.yMax = geotransform[3]
        self.yMin = geotransform[3] + nRows*geotransform[5]

def ReadRaster(rasterFile):
    ds = gdal.Open(rasterFile)
    band = ds.GetRasterBand(1)
    data = band.ReadAsArray()
    xsize = band.XSize
    ysize = band.YSize
    
    noDataValue = band.GetNoDataValue()
    geotrans = ds.GetGeoTransform()
    
    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    #print srs.ExportToProj4()
    if noDataValue is None:
        noDataValue = -9999
    return Raster(ysize, xsize, data, noDataValue, geotrans, srs) 

def WriteAscFile(filename, data, xsize, ysize, geotransform, noDataValue):
    header = """NCOLS %d
NROWS %d
XLLCENTER %f
YLLCENTER %f
CELLSIZE %f
NODATA_VALUE %f
""" % (xsize, ysize, geotransform[0] + 0.5*geotransform[1], geotransform[3]-(ysize-0.5)*geotransform[1], geotransform[1], noDataValue)
        
    f = open(filename, 'w')
    f.write(header)
    for i in range(0, ysize):
        for j in range(0, xsize):
            f.write(str(data[i][j]) + "\t")
        f.write("\n")
    f.close() 
    
def WriteGTiffFile(filename, nRows, nCols, data, geotransform, srs, noDataValue, gdalType):
    format = "GTiff"
    driver = gdal.GetDriverByName(format)
    ds = driver.Create(filename, nCols, nRows, 1, gdalType)
    ds.SetGeoTransform(geotransform)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).SetNoDataValue(noDataValue)
    ds.GetRasterBand(1).WriteArray(data)
    ds = None

def WriteGTiffFileByMask(filename, data, mask, gdalType):
    format = "GTiff"
    driver = gdal.GetDriverByName(format)
    ds = driver.Create(filename, mask.nCols, mask.nRows, 1, gdalType)
    ds.SetGeoTransform(mask.geotrans)
    ds.SetProjection(mask.srs.ExportToWkt())
    ds.GetRasterBand(1).SetNoDataValue(mask.noDataValue)
    ds.GetRasterBand(1).WriteArray(data)
    ds = None
def NashCoef(qObs, qSimu):
    n = len(qObs)
    ave = sum(qObs)/n
    a1 = 0
    a2 = 0
    for i in range(n):
        a1 = a1 + pow(qObs[i]-qSimu[i], 2)
        a2 = a2 + pow(qObs[i] - ave, 2)
    return 1 - a1/a2

def RMSE(list1, list2):
    n = len(list1)
    s = 0
    for i in range(n):
        s = s + pow(list1[i] - list2[i], 2)
    return math.sqrt(s/n)

def StdEv(list1):
    n = len(list1)
    av = sum(list1)/n
    s = 0
    for i in range(n):
        s = s + pow(list1[i] - av, 2)
    return math.sqrt(s/n)

def ContinuousGRID(raster,i,j,idx):
    nrows,ncols = raster.shape
    value = raster[i][j]
    #idx = []
    for di in [-1,0,1]:
        for dj in [-1,0,1]:
            if i+di >= 0 and i+di < nrows and j+dj >= 0 and j+dj < ncols:
                if raster[i+di][j+dj] == value and not(di == dj and di == 0):
                    if not [i+di,j+dj] in idx:
                        idx.append([i+di,j+dj])
                        ContinuousGRID(raster,i+di,j+dj,idx)
    #idx = list(set(idx))
    #return idx
    
def RemoveLessPts(RasterFile,num,OutputRaster):
    raster = ReadRaster(RasterFile).data
    nrows,ncols = raster.shape
    nodata = ReadRaster(RasterFile).noDataValue
    geotrans = ReadRaster(RasterFile).geotrans
    
    for i in range(nrows):
        for j in range(ncols):
            if raster[i][j] ==1:
                tempIdx = []
                ContinuousGRID(raster,i,j,tempIdx)
                tempIdx = list(set(tempIdx))
                count = tempIdx.__len__()
                for rc in tempIdx:
                    raster[rc[0]][rc[1]] = count
    for i in range(nrows):
        for j in range(ncols):
            if raster[i][j] <= int(num):
                raster[i][j] = nodata
            else:
                raster[i][j] = 1
    WriteAscFile(OutputRaster,raster,ncols,nrows,geotrans,nodata)
def RemoveLessPtsMtx(raster,nodata,num):
    nrows,ncols = raster.shape
    DelIdx = []
    for i in range(nrows):
        for j in range(ncols):
            if raster[i][j] ==1:
                tempIdx = []
                ContinuousGRID(raster,i,j,tempIdx)
                tempIdx = list(set(tempIdx))
                count = len(tempIdx)
                for rc in tempIdx:
                    raster[rc[0]][rc[1]] = count
    for i in range(nrows):
        for j in range(ncols):
            if raster[i][j] != nodata:
                if raster[i][j] <= int(num):
                    raster[i][j] = nodata
                    DelIdx.append([i,j])
                else:
                    raster[i][j] = 1
    return (DelIdx,raster)

def GRID2ASC(GRID,ASC):
    grid = ReadRaster(GRID).data
    nodata = ReadRaster(GRID).noDataValue
    #print nodata
    geotrans = ReadRaster(GRID).geotrans
    nrows,ncols = grid.shape
    temp = numpy.ones((nrows,ncols))
    temp = temp * -9999
    for i in range(nrows):
        for j in range(ncols):
            if grid[i][j] == nodata or grid[i][j] == 0:
                temp[i][j] = -9999
            else:
                temp[i][j] = grid[i][j]
    WriteAscFile(ASC, temp,ncols,nrows,geotrans,-9999.0)    
def GetUniqueValues(RasterFile):
    raster = ReadRaster(RasterFile).data
    nodata = ReadRaster(RasterFile).noDataValue
    #geotrans = ReadRaster(RasterFile).geotrans
    nrows,ncols = raster.shape
    value = []
    for i in range(nrows):
        for j in range(ncols):
            if raster[i][j] != nodata:
                if not (raster[i][j] in value):
                    value.append(raster[i][j])
    value = list(set(value))
    return value
def NearCells(raster,nodata,row,col):
    nrows,ncols = raster.shape
    nearcell = []
    for di in [-1,0,1]:
        for dj in [-1,0,1]:
            ni = row + di
            nj = col + dj
            if ni >= 0 and ni < nrows and nj >=0 and nj < ncols and raster[ni][nj] != nodata:
                nearcell.append([ni,nj])
    return nearcell

def isEdge(raster,row,col,nodata):
    nrows,ncols = raster.shape
    curvalue = raster[row][col]
    if (row == 0 or row == nrows-1 or col == 0 or col == ncols-1) and (curvalue != nodata):
        return True
    elif curvalue == nodata:
        return False
    else:
        nodatacount = 0
        valuecount = 0
        for di in [-1,0,1]:
            for dj in [-1,0,1]:
                ni = row + di
                nj = col + dj
                if raster[ni][nj] == nodata:
                    nodatacount = nodatacount + 1
                elif raster[ni][nj] != curvalue:
                    valuecount = valuecount + 1
        if valuecount > 1 or nodatacount > 0:
            #print count
            return True
        else:
            return False

def ExtractBoundary(raster,nodata,geotrans):
    nrows,ncols = raster.shape
    Boundary = numpy.ones((nrows,ncols))
    Boundary = Boundary * -9999
    for i in range(nrows):
        for j in range(ncols):
            if isEdge(raster,i,j,nodata):
                Boundary[i][j] = 1
    num,Boundary = simplifyBoundary(Boundary,nodata,geotrans)
    while num != 0:
        num,Boundary = simplifyBoundary(Boundary,nodata,geotrans)
    return Boundary
def getDir(fromPt,toPt):
    di = toPt[0]-fromPt[0]
    dj = toPt[1]-fromPt[1]
    for key in DIR_ITEMS.keys():
        if DIR_ITEMS[key] == (di,dj):
            return DIR_VALUES.index(key)
def EliminateDanglePoint(raster,nodata):
    nrows,ncols = raster.shape
    dangle = 0
    for i in range(nrows):
        for j in range(ncols):
            if raster[i][j] != nodata:
                temp = NearCells(raster,nodata,i,j)
                curNum = len(temp)
                
                if curNum in [0,1,2]:
                    raster[i][j] = nodata
                    dangle = dangle + 1
                if curNum == 3:
                    temp.remove([i,j])
                    idx1 = getDir([i,j],temp[0])
                    idx2 = getDir([i,j],temp[1])
                    if abs(idx1-idx2)==1 or abs(idx1-idx2)==7:
                        raster[i][j] = nodata
                    dangle = dangle + 1
               
    return (dangle,raster)
def thin(raster,geotrans,tempdir):
    arcpy.gp.overwriteOutput = 1
    arcpy.CheckOutExtension("spatial")
    nrows,ncols = raster.shape
    WriteAscFile(tempdir + os.sep + "tempBoundary.asc", raster,ncols,nrows,geotrans,-9999)
    arcpy.ASCIIToRaster_conversion(tempdir + os.sep + "tempBoundary.asc", tempdir + os.sep + "tempBnd","INTEGER")
    thinfile = arcpy.sa.Thin(tempdir + os.sep + "tempBnd","NODATA","","SHARP",geotrans[1])
    thinfile.save(tempdir + os.sep + "tempBndThin")
    GRID2ASC(tempdir + os.sep + "tempBndThin",tempdir + os.sep + "tempBndThin.asc")
    return ReadRaster(tempdir + os.sep + "tempBndThin.asc").data
    
def simplifyBoundary(raster,nodata,geotrans):
    nrows,ncols = raster.shape
    num = [0,0,0,0,0,0,0,0,0]
    dangle,raster = EliminateDanglePoint(raster,nodata)
    #WriteAscFile(r'E:\MasterBNU\RillMorphology\20150130\2Rill\SnakeICC4.asc', raster,ncols,nrows,geotrans,-9999)
    dangleCount = 0
    while dangle != 0 and dangleCount < 3:
        dangle,raster = EliminateDanglePoint(raster,nodata)
        dangleCount = dangleCount + 1 
    for i in range(nrows):
        for j in range(ncols):
            if raster[i][j] != nodata:
                nearcell = NearCells(raster,nodata,i,j)
                curNum = len(nearcell)
                num[curNum-1] = num[curNum-1] + 1
                if curNum in [0,1,2]:
                    raster[i][j] = nodata
                if curNum == 3:
                    nearcell.remove([i,j])
                    idx1 = getDir([i,j],nearcell[0])
                    idx2 = getDir([i,j],nearcell[1])
                    if abs(idx1-idx2)==1 or abs(idx1-idx2)==7:
                        raster[i][j] = nodata
                if curNum >= 4:
                    if ([i+1,j+1] in nearcell or [i-1,j+1] in nearcell) and [i,j+1] in nearcell:
                        raster[i][j+1] = nodata
                    elif ([i+1,j-1] in nearcell or [i-1,j-1] in nearcell) and [i,j-1] in nearcell:
                        raster[i][j-1] = nodata
                    elif ([i-1,j+1] in nearcell or [i-1,j-1] in nearcell) and [i-1,j] in nearcell:
                        raster[i-1][j] = nodata
                    elif ([i+1,j+1] in nearcell or [i+1,j-1] in nearcell) and [i+1,j] in nearcell:
                        raster[i+1][j] = nodata
    #WriteAscFile(r'E:\MasterBNU\RillMorphology\20150130\2Rill\SnakeICC4.asc', raster,ncols,nrows,geotrans,-9999)
    #print num
    return (num[3],raster)
def isAdjacent(ptStd,ptEnd):
    flag = 0
    for i in [-1,0,1]:
        for j in [-1,0,1]:
            crow = ptStd[0]+i
            ccol = ptStd[1]+j
            if [crow,ccol] == ptEnd:
                flag = 1
                return True
    if flag == 0:
        return False
def InterpLine(ptStd,ptEnd):
    Srow,Scol = ptStd
    Erow,Ecol = ptEnd
    Sr = min(Srow,Erow)
    Er = max(Srow,Erow)
    Sc = min(Scol,Ecol)
    Ec = max(Scol,Ecol)
    Idxs = []
    if isAdjacent(ptStd,ptEnd):
        return Idxs
    elif Srow == Erow:
        for i in range(Sc + 1,Ec):
            Idxs.append([Srow,i])
    elif Scol == Ecol:
        for i in range(Sr + 1,Er):
            Idxs.append([i,Scol])
    else:
        for i in range(Sc + 1,Ec):
            #crow = int(round((float(Erow-Srow)/float(Ecol-Scol))*(i - Scol)))
            crow = int(round(float(Erow-Srow)/float(Ecol-Scol)*(i - Scol)+Srow))
            Idxs.append([crow,i])
        for j in range(Sr + 1,Er):
            ccol = int(round(float(Ecol-Scol)/float(Erow-Srow)*(j - Srow) + Scol))
            Idxs.append([j,ccol])
    uniqueIdxs = []
    for idx in Idxs:
        if idx not in uniqueIdxs:
            uniqueIdxs.append(idx)
    uniqueIdxs.sort()
    return uniqueIdxs




##  End Utility Functions ##

## DEM Preprocessing  ##
def UtilHydroFiles(DEMsrc, folder):
    DEMbuf = folder + os.sep + "DEMbuf.tif"
    DEMfil = folder + os.sep + "DEMfil.tif"
    SlopeFile = folder + os.sep + "slope.tif"
    SOSFile = folder + os.sep + "sos.tif"
    AspectFile = folder + os.sep + "aspect.tif"
    FlowDirFile = folder + os.sep + "flowdir.tif"
    FlowAccFile = folder + os.sep + "flowacc.tif"
    CurvFile = folder + os.sep + "curv.tif"
    CurvProfFile = folder + os.sep + "curvprof.tif"
    CurvPlanFile = folder + os.sep + "curvplan.tif"
    
    
    print "Calculating fundamental hydrological parameters from DEM using Arcpy and TauDEM..."
    env.workspace = folder
    arcpy.gp.overwriteOutput = 1
    arcpy.CheckOutExtension("Spatial")
    ## Set the source dem with one cell buffer to 
    ## avoid NODATA around the edges
    print "   --- DEM buffer 1 cell..."
    dem_des = arcpy.gp.describe(DEMsrc)
    cellsize = max(dem_des.MeanCellWidth,dem_des.MeanCellHeight)
    extent_src = dem_des.Extent
    extent_buf = arcpy.Extent(dem_des.Extent.XMin - cellsize,dem_des.Extent.YMin - cellsize,dem_des.Extent.XMax + cellsize,dem_des.Extent.YMax + cellsize)
    env.extent = extent_buf
    env.cellSize = cellsize
    Exec = "Con(IsNull(\"%s\"),FocalStatistics(\"%s\", NbrRectangle(3, 3, \"CELL\"), \"MEAN\", \"DATA\"),\"%s\")" % (DEMsrc, DEMsrc, DEMsrc)
    arcpy.gp.RasterCalculator_sa(Exec, DEMbuf)
    print "   --- fill depression..."
    env.extent = dem_des.Extent
    demfil = arcpy.sa.Fill(DEMsrc)
    demfil.save(DEMfil)
    print "   --- calculating aspect, slope, curvature, flow direction, flow accumulation..."
    Aspect = arcpy.sa.Aspect(DEMfil)
    Slope = arcpy.sa.Slope(DEMfil,"DEGREE")
    
    Flowdir = arcpy.sa.FlowDirection(DEMfil,"NORMAL")
    Curvature = arcpy.sa.Curvature(DEMfil,"",CurvProfFile,CurvPlanFile)
    Curvature.save(CurvFile)
    Slope.save(SlopeFile)
    Aspect.save(AspectFile)
    Flowdir.save(FlowDirFile)
    SOS = arcpy.sa.Slope(SlopeFile,"DEGREE")
    SOS.save(SOSFile)
    #FlowLen = arcpy.sa.FlowLength(FlowDirFile,"DOWNSTREAM")
    #FlowLen.save("flowlen")
    FlowAcc = arcpy.sa.FlowAccumulation(FlowDirFile,"","FLOAT")
    FlowAcc.save(FlowAccFile)
    #Basin = arcpy.sa.Basin(FlowDirFile)
    #Basin.save("basin")
    #arcpy.RasterToPolygon_conversion("basin","basin.shp","NO_SIMPLIFY","VALUE")
    
    
    
    return (DEMbuf,DEMfil,SlopeFile,SOSFile,AspectFile,FlowDirFile,FlowAccFile,CurvFile,CurvProfFile,CurvPlanFile)

## End DEM Preprocessing ##

## Folder and file Functions ##
def currentPath():
    path = sys.path[0]
    if os.path.isdir(path):
        return path
    elif os.path.isfile(path):
        return os.path.dirname(path)
def mkdir(dir):
    if not os.path.exists(dir):
        os.mkdir(dir)
def makeResultFolders(rootdir):
    print "Making results' folders..."
    if not os.path.isdir(rootdir):
        if rootdir != "":
            mkdir(rootdir)
        else:
            rootdir = currentPath() + os.sep + "RillPyResults"
            mkdir(rootdir)
    PreprocessDir = rootdir + os.sep + "1Preprocess"
    tempDir = rootdir + os.sep + "0Temp"
    RillExtDir = rootdir + os.sep + "2Rill"
    StatsDir = rootdir + os.sep + "3Stats"
    mkdir(PreprocessDir)
    mkdir(tempDir)
    mkdir(RillExtDir)
    mkdir(StatsDir)
    return (tempDir,PreprocessDir,RillExtDir,StatsDir)
## End Folder and file Functions ##