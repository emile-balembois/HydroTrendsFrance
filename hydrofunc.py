"""
Copyright (c) [2024] [Quentin DASSIBAT]

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""



def extract_Rasterbbox(srcFile):

    """
    srcFile: path/to/source/raster/file.tif [string]

    output : bbox of srcFile as a string "xmin ymin xmax ymax" [string]
    """

    from osgeo import gdal
    gdal.UseExceptions()

    src = gdal.Open(srcFile)

    upx, xres, xskew, upy, yskew, yres = src.GetGeoTransform()
    cols = src.RasterXSize
    rows = src.RasterYSize
     
    ulx = upx + 0*xres + 0*xskew
    uly = upy + 0*yskew + 0*yres
     
    llx = upx + 0*xres + rows*xskew
    lly = upy + 0*yskew + rows*yres
     
    lrx = upx + cols*xres + rows*xskew
    lry = upy + cols*yskew + rows*yres
     
    urx = upx + cols*xres + 0*xskew
    ury = upy + cols*yskew + 0*yres

    bbox = f"{llx} {lly} {urx} {ury}" #xmin (llx) ymin (lly) xmax (urx) ymax (ury)

    return bbox



def extract_Vectorbbox(srcFile):

    """
    srcFile: path/to/source/vector/file.gpkg [string] or any fiona-driver compatible format

    output : bbox of srcFile as a string "xmin ymin xmax ymax" [string]
    """

    import geopandas as gpd

    gdf = gpd.read_file(srcFile)
    bbox = f"{gdf.total_bounds[0]} {gdf.total_bounds[1]} {gdf.total_bounds[2]} {gdf.total_bounds[3]}"

    del gdf

    return bbox


def reproject_raster(srcFile,dstFile,dstEPSG):

    """
    srcFile: path/to/source/raster/file.tif [string]
    dstFile: path/to/destination/raster/file.tif [string]
    dstEPSG: EPSG code to be used when reprojecting [int]
    """

    import os
    from osgeo import gdal, osr
    gdal.UseExceptions()

    #Get the current EPSG and height/width of srcFile

    src = gdal.Open(srcFile)
    projection = src.GetProjection()
    srs = osr.SpatialReference()
    srs.ImportFromWkt(projection)
    srcEPSG = srs.GetAttrValue('AUTHORITY', 1)
    srcWIDTH = src.RasterXSize
    srcHEIGTH = src.RasterYSize
    src = None

    #Reproject raster to dstEPSG
    
    cmd = f"gdalwarp -overwrite -s_srs EPSG:{str(srcEPSG)} -t_srs EPSG:{str(dstEPSG)} -r near -ts srcWIDTH srcHEIGTH -of GTiff {srcFile} {dstFile}"
    os.system(cmd)
    
    return


def reproject_bbox(bbox,srcEPSG,dstEPSG):

    """
    bbox: coordinates as a string "xmin ymin xmax ymax" [string]
    srcEPSG: source ESPG corresponding to bbox parameter [int]
    dstEPSG: destination EPSG in which to reproject bbox [int]

    output : coordinates as a string "xmin ymin xmax ymax" projected in dstEPSG [string]
    """

    import pyproj
    import shapely

    transformer = Transformer.from_crs(f"EPSG:{srcEPSG}", f"EPSG:{dstEPSG}", always_xy=True)
    lbbox = bbox.split()
    sbbox = shapely.geometry.box(lbbox[0], lbbox[1], lbbox[2], lbbox[3])
    tbbox = transformer.transform(sbbox.bounds[0], sbbox.bounds[1], sbbox.bounds[2], sbbox.bounds[3])

    dstbbox = ' '.join(str(coord) for coord in tbbox)

    return dstbbox
    

def request_osm_feature(bbox,bboxEPSG,tags,dstFile):

    """
    This function uses osmnx library to request an OSM feature based on the parameter tag and over a specified AoI.

    bbox: coordinates as a string "xmin ymin xmax ymax" to define the request's spatial extent [string]
    tags: dictionary containing the key and its feature to be requested [Python's dict] Format is: {'key':'feature'} with only one key and one feature at a time.
    dstFile: /path/to/destination/layer.gpkg containing the geoDataFrame with requested objects projected in bboxEPSG [string]
    bboxEPSG: EPSG of the bbox parameter in which to project dstFile [int] Note that osmnx used EPSG:4326 to this function reprojects srcEPSG into it before request
    """

    import osmnx as ox
    import geopandas as gpd
    
    #Reproject bbox if needed
    if bboxEPSG != 4326:
        newbbox = reproject_bbox(bbox,bboxEPSG,4326)
    else:
        newbbox = bbox

    #Request 
    lbbox = newbbox.split()
    xmin, ymin, xmax, ymax = [float(coord) for coord in lbbox]
    north = ymax
    south = ymin
    east = xmax
    west = xmin
    
    try:
        try:
            gdf = ox.features.features_from_bbox(north, south, east, west, tags=tags)
        except TypeError:
            try:
                gdf = ox.features.features_from_bbox((west, south, east, north), tags=tags)
            except TypeError:
                gdf = ox.features.features_from_bbox(bbox=(north, south, east, west), tags=tags)
        
        gdf.set_crs(epsg=4326, inplace=True)
        #Keep only the geometry column and the POINT-geometry rows and the column corresponding to the feature called in 'tags' parameter
        key = list(tags.keys())[0]
        gdfc = gdf[['geometry',f"{str(key)}"]]
        gdfc.loc[:,'feature'] = list(gdfc[f"{str(key)}"]) #rename "key" column with "feature"
        gdfc.drop(f"{str(key)}",axis=1,inplace=True)
        gdfcc = gdfc.loc[gdfc['geometry'].geom_type == 'Point'] #keep only point geometries
        gdfcc.reset_index(inplace=True,drop=True)
        #Reproject gdf if needed 
        if bboxEPSG != 4326:
            res = gdfcc.to_crs(f"EPSG:{str(bboxEPSG)}")
        else:
            res = gdfcc.copy()
        #Write to disk as dstFile
        res.to_file(dstFile)

    except (ox._errors.InsufficientResponseError,ox._errors.ResponseStatusCodeError) as e:
        print(f"OSMnx error occurred: {e} for tags {tags}")
        pass
    

    return 
    
        


def request_locations_hubeau(bbox,dstFile,operating,tRange=None):

    """
    Makes a request to https://hubeau.eaufrance.fr/api/v2/hydrometrie/referentiel/stations? and returns a geoDataFrame with station codes
    with colomuns ['code_station','date_ouverture_station','date_fermeture_station','geometry']

    bbox: coordinates as a string "xmin ymin xmax ymax" to define the request's spatial extent [string]
    dstFile: /path/to/destination/layer.gpkg containing the geoDataFrame projected in EPSG:4326 [string]
    operating: geoDataFrame will be filtered to only still operating stations if True, or will keep all returned stations if False [python object]
    tRange [optionnal] [list]: default is None, meaning their is no time range specified (sation observations are extracted from each station's openning date to present date or to the station's closing date). If tRange has both values specified, e.g. ["yyyy","yyyy"], values are retrieved for this time range.
    """

    #Import libraries
    import geopandas as gpd
    import pandas as pd
    import requests
    import json
    import shapely
    import datetime

    #Split coordinates string 
    l = bbox.split()
    xmin = l[0]
    ymin = l[1]
    xmax = l[2]
    ymax = l[3]
    
    print("Request to hubeau.eaufrance.fr")
    size = 10000 #maximum depth of the json response from hubeau.eaufrance.fr 
    url = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/referentiel/stations"
    params = {
        "size": size,
        "pretty": "",
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
    }
    r = requests.get(url, params=params, allow_redirects=True)
    if r.status_code not in (200, 206):
        raise Exception(f"In request to {r.url} :\nstatus code = {r.status_code}")
    
    #Convert data from json to dataframe
    
    data = json.loads(r.content)
    df_stations = pd.json_normalize(data['data'])
    df_stations['longitude_station'] = df_stations['longitude_station'].astype("string")
    df_stations['latitude_station'] = df_stations['latitude_station'].astype("string")
    df_stations['coordonnees']="POINT ("+df_stations['longitude_station']+" "+df_stations['latitude_station']+")"
    geometry = df_stations['coordonnees'].map(shapely.wkt.loads)
    df_stations.drop('coordonnees', axis=1, inplace=True)
    gdf_stations = gpd.GeoDataFrame(df_stations, crs="EPSG:4326", geometry=geometry)
    
    #Filter dataframe to only specific columns and drop duplicates
    champs = ['code_station','date_ouverture_station','date_fermeture_station','geometry']
    gdf_stations1 = gdf_stations[champs]
    gdf_stations1.drop_duplicates(subset='code_station',inplace=True)
    gdf_stations1.reset_index(drop=True,inplace=True)

    #Export dataframe without filtering timeRange to keep all stations matching the AoI
    gdf_stations1.to_file(f"{dstFile[:-5]}_NoTimeRangeConstraint.gpkg")

    #Filter dataframe according to the value of operating parameter and set integer index
    if operating is True:
        m = gdf_stations1['date_fermeture_station'].isnull()
        gdf_stations2 = gdf_stations1.loc[m]
        m = gdf_stations2['date_ouverture_station'].notna()
        gdf_stations3 = gdf_stations2.loc[m]
        gdf_stations3.set_index(pd.Index([i for i in range(len(gdf_stations3))]),inplace=True)
    else:
        gdf_stations3 = gdf_stations1.copy()
        gdf_stations3.set_index(pd.Index([i for i in range(len(gdf_stations3))]),inplace=True)
    
    #Filter dataframe according to the value of tRange parameter and reset index
    
    if tRange is not None:

        deb_string = str(tRange[0])
        deb_datetime = datetime.datetime.strptime(deb_string, '%Y')
        deb_float = float(deb_datetime.year)
        fin_string = str(tRange[1])
        fin_datetime = datetime.datetime.strptime(fin_string, '%Y')
        fin_float = float(fin_datetime.year)

        gdf_stations1['date_ouverture_station'] = pd.to_datetime(gdf_stations1['date_ouverture_station'], errors='coerce')
        gdf_stations1['date_fermeture_station'] = pd.to_datetime(gdf_stations1['date_fermeture_station'], errors='coerce')
        
        gdf_stations1['annee_ouverture_station'] = gdf_stations1['date_ouverture_station'].dt.year
        gdf_stations1['annee_fermeture_station'] = gdf_stations1['date_fermeture_station'].dt.year

        tmp = gdf_stations1.loc[gdf_stations1['annee_fermeture_station'].isna()]
        tmp.loc[:,'annee_fermeture_station'] = fin_datetime.year
        #tmp2 = gdf_stations1.loc[gdf_stations1['annee_fermeture_station'].isnull()]
        #tmp2.loc[:,'annee_fermeture_station'] = fin_datetime.year
        tmp3 = gdf_stations1.loc[~gdf_stations1['annee_fermeture_station'].isna()]
        tmp4 = gdf_stations1.loc[~gdf_stations1['annee_fermeture_station'].isnull()]

        gdf_stations2 = pd.concat([tmp,tmp3,tmp4])
        gdf_stations2['annee_ouverture_station'] = gdf_stations2['annee_ouverture_station'].astype(float)
        gdf_stations2['annee_fermeture_station'] = gdf_stations2['annee_fermeture_station'].astype(float)
        gdf_stations2.set_index(pd.Index([i for i in range(len(gdf_stations2))]),inplace=True)

        m = (gdf_stations2['annee_ouverture_station'] <= deb_float) & (gdf_stations2['annee_fermeture_station'] >= fin_float)
        
        gdf_stations3 = gdf_stations2.loc[m]

        gdf_stations1.drop_duplicates(subset='code_station',inplace=True)
        gdf_stations3.drop_duplicates(subset='code_station',inplace=True)
        print(f"{str(len(gdf_stations1))} stations matching the AoI among which {str(len(gdf_stations3))} matching the time range")

        with open(f"log.txt", 'a') as file:
            file.write(f"{str(len(gdf_stations1))} stations matching the AoI among which {str(len(gdf_stations3))} matching the time range\n")

    else:
        
        gdf_stations3 = gdf_stations1.copy()
    
    #Write dataframe to disk as .gpkg
    gdf_stations3.to_file(f"{dstFile[:-5]}_{str(tRange[0])}{str(tRange[1])}.gpkg")

    return


def requestBackend_observations_hubeau(stationCode,start,end):

    """
    stations: code_station [string]
    start: YYYY-MM-DD [string]
    end: YYYY-MM-DD [string]
    """

    #Import libraries 
    import datetime
    import geopandas as gpd
    import pandas as pd
    import requests
    import json
    import numpy as np

    #Request observations
    
    grandeur = "QmnJ"
    size = 10000
    
    url = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"
    params = {
        "size": size,
        "pretty": "",
        "code_entite": str(stationCode),
        "grandeur_hydro_elab": grandeur,
        "date_debut_obs_elab": str(start),
        "date_fin_obs_elab": str(end),
    }

    r = requests.get(url, params=params, allow_redirects=True)
        
    if  r.status_code in (200, 206):
    
        data = json.loads(r.content)
        df_response = pd.json_normalize(data['data'])

        #Clear response dataframe and store it if it is not empty

        if df_response.empty is not True:

            #Select specific fields
            fields = ['code_station','date_obs_elab','resultat_obs_elab','grandeur_hydro_elab','libelle_statut']
            dfc = df_response[fields]
            del df_response
        
        else:
            print(f"null response from url {r.url}")
            
            frames = {'code_station':[str(stationCode)],
                      'date_obs_elab':[np.float32(np.nan)],
                      'resultat_obs_elab':[np.float32(np.nan)],
                      'grandeur_hydro_elab':[np.float32(np.nan)],
                      'libelle_statut':[np.float32(np.nan)]}
            dfc = pd.DataFrame(frames)
    
    else:
        print(f"error {r.status_code} from url {r.url}")
        
        frames = {'code_station':[str(stationCode)],
                      'date_obs_elab':[np.float32(np.nan)],
                      'resultat_obs_elab':[np.float32(np.nan)],
                      'grandeur_hydro_elab':[np.float32(np.nan)],
                      'libelle_statut':[np.float32(np.nan)]}
        dfc = pd.DataFrame(frames)

    
    return dfc



def requestFrontend_observations_hubeau(srcFile,dstFile,tRange=None):

    """
    Makes a request to https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab? and returns a geoDataFrame with station observations (Mean Daily Flows)
    with colomuns ['code_station','date_obs_elab','resultat_obs_elab','geometry']
    
    tRange [optionnal] [list]: default is None, meaning their is no time range specified (sation observations are extracted from each station's openning date to present date or to the station's closing date). If tRange has both values specified, e.g. ["yyyy-mm-dd","yyyy-mm-dd"], values are retrieved for this time range.

    srcFile: /path/to/source/layer.gpkg containing the geoDataFrame of station codes #index must be integers [string]
    dstFile: /path/to/destination/layer.gpkg [string]
    """

    #Import libraries 
    import numpy as np
    import datetime
    import geopandas as gpd
    import pandas as pd
    import requests
    import json

    #Read station location file
    gdf = gpd.read_file(srcFile)
    
    #Itération sur les stations

    stations_observ = []
    
    for s in range(len(gdf)):
        
        stas = gdf.loc[s,'code_station']
        geom = gdf.loc[s,'geometry']
        print("Station",stas)
        
        #Calcul du nombre de requêtages nécessaires 

        if tRange is None:
        
            ##Selon la date d'ouverture de la station (par défaut) : depuis la date d'ouverture jusqu'à aujourd'hui ou jusqu'à la date de fermeture
            
            Nmax = 10000 #profondeur max de la requête
            
            mask = gdf['code_station'].str.match(str(stas))
            ouv = list(gdf.loc[mask,"date_ouverture_station"])
            ouv_string = ouv[0][:10]
            ouv_datetime = datetime.datetime.strptime(ouv_string, '%Y-%m-%d')
            
            ajd = str(datetime.datetime.now())
            ajd_string = ajd[:10]
            ajd_datetime = datetime.datetime.strptime(ajd_string, '%Y-%m-%d')
            arret = list(gdf.loc[mask,"date_ouverture_station"])
            if len(arret) != 0:
                arret_string = ouv[0][:10]
                arret_datetime = datetime.datetime.strptime(arret_string, '%Y-%m-%d')
                if arret_datetime < ajd_datetime:
                    ferm_datetime = arret_datetime
                else:
                    ferm_datetime = ajd_datetime
            else:
                ferm_datetime = ajd_datetime 
        
            delta = ferm_datetime - ouv_datetime
            
            nb_iter = np.trunc(delta.days/Nmax)+1 #partie entière du nombre d'itérations

        else:
            
            ##Selon la plage temporelle spécifiée
            
            Nmax = 10000 #profondeur max de la requête
            
            ouv_string = tRange[0]
            ouv_datetime = datetime.datetime.strptime(ouv_string, '%Y-%m-%d')
            
            ferm_string = tRange[1]
            ferm_datetime = datetime.datetime.strptime(ferm_string, '%Y-%m-%d')
        
            delta = ferm_datetime - ouv_datetime
            
            nb_iter = np.trunc(delta.days/Nmax)+1 #partie entière du nombre d'itérations
        
        #Requêtages et concaténations successives
        
        print("closing_datetime",ferm_datetime)
        print("openning_datetime",ouv_datetime)
        
        for i in range(int(nb_iter)):
            
            save_deb = 0
            fin = 0
            
            incr = datetime.timedelta(days=(i+1)*Nmax)
            
            if ferm_datetime-incr <= ouv_datetime:
                
                tmp = str(ouv_datetime)
                deb = tmp[:10]
                print("deb_obs",deb)
                
                tmp = str(ferm_datetime - datetime.timedelta(days=i*Nmax))
                fin = tmp[:10]
                print("fin_obs",fin)
                
                df_observ = requestBackend_observations_hubeau(stas,deb,fin)
                #Add geometry column
                df_observ.loc[:,'geometry'] = geom
                stations_observ.append(df_observ)
                del df_observ
            
            else:
                
                tmp = str(ferm_datetime - datetime.timedelta(days=(i+1)*Nmax-1))
                deb = tmp[:10]
                print("deb_obs",deb)
                
                tmp = str(ferm_datetime - datetime.timedelta(days=i*Nmax))
                fin = tmp[:10]
                print("fin_obs",fin)
                
                df_observ = requestBackend_observations_hubeau(stas,deb,fin)
                #Add geometry column
                df_observ.loc[:,'geometry'] = geom
                stations_observ.append(df_observ)
                del df_observ
        

    #Concatenate every dataframes of all stations and convert to geodataframe
    df_stations = pd.concat(stations_observ)
    gdf_stations = gpd.GeoDataFrame(df_stations, crs="EPSG:4326")
    gdf_stations.set_geometry('geometry')

    #Write to disk 
    gdf_stations.to_file(dstFile)

    #Compute the number of stations successfully fetched against the total number of stations requested
    gdf_stations_nonull = gdf_stations.dropna(subset='resultat_obs_elab',axis=0)
    fetched = len(list(set(gdf_stations_nonull['code_station'])))
    requested = len(list(set(gdf_stations['code_station'])))
    print(f"{str(requested)} stations where requested observations among which {str(fetched)} stations were fetched")
    with open(f"log.txt", 'a') as file:
        file.write(f"{str(requested)} stations where requested observations among which {str(fetched)} stations were fetched\n")

    return



def compute_MeanMonthlyFlow_average(stationCode,stationsLayer,dstLayer,period,generate_plot):
    
    """
    This function computes the average MMF and standard deviation of MMF over a given period for a given station, e.g. the average monthly flow in january on the period 2000-2020 for station i, and the standard deviation associated with this average MMF.
    Another function, compute_MeanMonthlyFlow_all() is designed to compute MMF separately for each month in the period (without averaging over the period). 
    
    stationCode: code of the station to be analyzed [string]
    stationsLayer: source layer that is the geodataframe with stations observations #must be a gdf already loaded [geopandas object]
    where columns must be labelled as follow ['code_station','date_obs_elab','resultat_obs_elab','grandeur_hydro_elab','libelle_statut','geometry']
    period: time window to perform the analysis upon given as a list [start,end] with date format YYYY [list]
    generate_plot: if set to True, the function also creates a plot of MMF along the period [python object]
    
    dstLayer: /path/to/destination/layer.gpkg that is a geodataframe with columns = ['code_station','MMFmu_#month_#period','MMFsigma_#month_#period','geometry']
    """
    
    import re
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    import datetime
    
    dfc_hydro = stationsLayer.copy()
    
    #Extraction des relevés hydro pour la station
    dfc_hydro.code_station = dfc_hydro.code_station.astype("string")
    dfc_cut = dfc_hydro.loc[dfc_hydro['code_station'].str.match(str(stationCode))]
    dfc_cut.dropna(subset='resultat_obs_elab',axis=0,inplace=True)
    dfc_cut['date_obs_elab'] = dfc_cut['date_obs_elab'].astype("string")
    dfc_cut.reset_index(drop=True,inplace=True)

    if dfc_cut.empty is not True:
    
        #Grouper par mois et calculer la moyenne

        mu_Y = []
        sigma_Y = []
        
        for i in range(1,13):

            if i <= 9:
                dfc_cut2 = dfc_cut.loc[dfc_cut['date_obs_elab'].str.contains(f"-0{str(i)}-")]
            else:
                dfc_cut2 = dfc_cut.loc[dfc_cut['date_obs_elab'].str.contains(f"-{str(i)}-")]

            if dfc_cut2.empty is not True:
                mu = dfc_cut2['resultat_obs_elab'].mean(skipna=True)
                sigma = dfc_cut2['resultat_obs_elab'].std(skipna=True,ddof=1)
            else:
                mu = np.nan
                sigma = np.nan
            
            mu_Y.append(mu)
            sigma_Y.append(sigma)

            dfc_cut2 = dfc_cut2.iloc[0:0] #del df_month content
      
        #Gather monthly data in a dataframe and save it to disk as .gpkg
       
        dic = {'code_station':[stationCode],
            f"MMFmu_month1_{period[0]}{period[1]}":[mu_Y[0]],
            f"MMFmu_month2_{period[0]}{period[1]}":[mu_Y[1]],
            f"MMFmu_month3_{period[0]}{period[1]}":[mu_Y[2]],
            f"MMFmu_month4_{period[0]}{period[1]}":[mu_Y[3]],
            f"MMFmu_month5_{period[0]}{period[1]}":[mu_Y[4]],
            f"MMFmu_month6_{period[0]}{period[1]}":[mu_Y[5]],
            f"MMFmu_month7_{period[0]}{period[1]}":[mu_Y[6]],
            f"MMFmu_month8_{period[0]}{period[1]}":[mu_Y[7]],
            f"MMFmu_month9_{period[0]}{period[1]}":[mu_Y[8]],
            f"MMFmu_month10_{period[0]}{period[1]}":[mu_Y[9]],
            f"MMFmu_month11_{period[0]}{period[1]}":[mu_Y[10]],
            f"MMFmu_month12_{period[0]}{period[1]}":[mu_Y[11]],
            f"MMFsigma_month1_{period[0]}{period[1]}":[sigma_Y[0]],
            f"MMFsigma_month2_{period[0]}{period[1]}":[sigma_Y[1]],
            f"MMFsigma_month3_{period[0]}{period[1]}":[sigma_Y[2]],
            f"MMFsigma_month4_{period[0]}{period[1]}":[sigma_Y[3]],
            f"MMFsigma_month5_{period[0]}{period[1]}":[sigma_Y[4]],
            f"MMFsigma_month6_{period[0]}{period[1]}":[sigma_Y[5]],
            f"MMFsigma_month7_{period[0]}{period[1]}":[sigma_Y[6]],
            f"MMFsigma_month8_{period[0]}{period[1]}":[sigma_Y[7]],
            f"MMFsigma_month9_{period[0]}{period[1]}":[sigma_Y[8]],
            f"MMFsigma_month10_{period[0]}{period[1]}":[sigma_Y[9]],
            f"MMFsigma_month11_{period[0]}{period[1]}":[sigma_Y[10]],
            f"MMFsigma_month12_{period[0]}{period[1]}":[sigma_Y[11]],
            'geometry':[dfc_cut.loc[0,'geometry']]
            }
            
        dfg = pd.DataFrame(dic)
        final_gdf = gpd.GeoDataFrame(dfg, crs="EPSG:4326")
        final_gdf.set_geometry('geometry',inplace=True)
        

        #Elaborate advanced statistics: monthly coefficient of variation (CoV=std/mean), annual mean, annual deviation, annual CoV

        final_gdf.loc[:,f'CoV_month1_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month1_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month1_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month2_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month2_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month2_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month3_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month3_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month3_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month4_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month4_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month4_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month5_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month5_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month5_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month6_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month6_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month6_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month7_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month7_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month7_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month8_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month8_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month8_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month9_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month9_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month9_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month10_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month10_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month10_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month11_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month11_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month11_{period[0]}{period[1]}"]
        final_gdf.loc[:,f'CoV_month12_{period[0]}{period[1]}'] = final_gdf[f"MMFsigma_month12_{period[0]}{period[1]}"]/final_gdf[f"MMFmu_month12_{period[0]}{period[1]}"]

        #Compute Mean Annual Flow
        col_list = [f"MMFmu_month{x}_{period[0]}{period[1]}" for x in range(1,13)]
        final_gdf_mean = final_gdf[col_list]
        final_gdfT = final_gdf_mean.T #gives a df with one column 'code_station' and former columns turned to rows
        final_gdfT.dropna(inplace=True) #drop rows with NaN values that may have been kept in mu and sigma calculations
        MAF = final_gdfT[0].mean()
        final_gdf.loc[:,f'MeanAnnualFlow_{period[0]}{period[1]}'] = MAF

        #Compute Mean Annual Deviation
        col_list = [f"MMFsigma_month{x}_{period[0]}{period[1]}" for x in range(1,13)]
        final_gdf_sigma = final_gdf[col_list]
        final_gdfT = final_gdf_sigma.T #gives a df with one column 'code_station' and former columns turned to rows
        final_gdfT.dropna(inplace=True) #drop rows with NaN values that may have been kept in mu and sigma calculations
        MAD = final_gdfT[0].std(ddof=1)
        final_gdf.loc[:,f'MeanAnnualDeviation_{period[0]}{period[1]}'] = MAD

        #Compute Mean Annual CoV
        final_gdf.loc[:,f'MeanAnnualCoV_{period[0]}{period[1]}'] = MAD/MAF
        
        #Write to disk 
        final_gdf.to_file(dstLayer)
        
        #Draw hydrogram if specified by generate_plot=True
        try :
            if generate_plot is True:

                fig, ax1 = plt.subplots()

                #Plot hydrogram on the left y-axis
                
                x_axis = [x+1 for x in range(12)]
                ax1.errorbar(x_axis, mu_Y, yerr = sigma_Y, fmt ='o', label='MMF', color='#1f77b4')
                #plt.xticks(x_axis)
                ax1.set_ylabel(f"Mean Monthly Flow [l.s-1]",fontsize=9, color='#1f77b4')
                ax1.set_xlabel('month',fontsize=9)
                ax1.tick_params(axis='y', labelcolor='#1f77b4')

                #Plot CoV on the right y-axis
                col_list = [f"CoV_month{x}_{period[0]}{period[1]}" for x in range(1,13)]
                final_gdf_sigma = final_gdf[col_list]
                final_gdfT = final_gdf_sigma.T #gives a df with one column 'code_station' and former columns turned to rows
                print(final_gdfT)
                cov_list = list(final_gdfT[0])
                print(cov_list)
                
                ax2 = ax1.twinx()
                ax2.plot(x_axis, cov_list, '4', label='CoV', color='#d62728', markersize=9)
                ax2.set_ylabel('Monthly Coefficients of Variation', color='#d62728',fontsize=9)
                ax2.tick_params(axis='y', labelcolor='#d62728')
                
                ax1.set_xticks(x_axis)
                ax1.set_xticklabels(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])
                ax2.set_yticks(np.arange(np.round(min(cov_list),decimals=2),np.round(max(cov_list),decimals=2),0.1))
                ax2.grid(True)
                
                fig.suptitle(f"Mean Monthly Flow and Variation of station {str(stationCode)} over the period {period[0]}-{period[1]}",fontsize=9)
                
                fig.text(0.03, 0.03, '(c) Q. DASSIBAT -- CC BY 4.0', fontsize=5, color='gray', va='bottom', ha='left')
                
                plt.savefig(f"./analysis/MMF_{stationCode}_{period[0]}{period[1]}.png",bbox_inches='tight',dpi=300)
                plt.close() #sinon à chaque appel de la fonction la figure est dessinée sur le même graphe

        except Exception as e :
            raise Exception(f"ERROR in drawing hydrograms, in func compute_MeanMonthlyFlow_average.\ncov_list = {cov_list}\n{e}")

        else:
            pass
            
        #else:
            
        #    print(f"Station {str(stationCode)} does not cover the range {str(period)}")

    else:
        pass

    try:
        final_gdf
    except:
        pass
    else:
        return final_gdf



def compute_MeanMonthlyFlow_all(stationCode,stationsLayer,dstLayer,period,epsgCode):
    
    """
    This function is designed to compute MMF separately for each month in the period (without averaging over the period). 
    
    stationCode: code of the station to be analyzed [string]
    stationsLayer: source layer that is the geodataframe with stations observations #must be a gdf already loaded [geopandas object]
    where columns must be labelled as follow ['code_station','date_obs_elab','resultat_obs_elab','grandeur_hydro_elab','libelle_statut','geometry']
    period: time window to perform the analysis upon given as a list [start,end] with date format YYYY [list]
    generate_plot: if set to True, the function also creates a plot of MMF along the period [python object]
    
    dstLayer: /path/to/destination/layer.gpkg that is a geodataframe with columns = ['date','MMF_mean','MMF_std','code_station','geometry']
    """
    
    import re
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    import datetime
    from shapely import wkt
    
    dfc_hydro = stationsLayer.copy()
    
    #Extraction des relevés hydro pour la station
    dfc_hydro.code_station = dfc_hydro.code_station.astype("string")
    dfc_cut = dfc_hydro[dfc_hydro.code_station.str.match(str(stationCode))]
    l1 = len(dfc_cut)
    dfc_cut.dropna(subset='resultat_obs_elab',axis=0,inplace=True)
    l2 = len(dfc_cut)
    print(f"{str(l1-l2)} null records out of out of {str(l1)} for station {stationCode}")

    if dfc_cut.empty is not True:
    
        #Grouper par mois et calculer la moyenne
        
        #Convertir la colonne date en objet datetime
        serie = dfc_cut['date_obs_elab'].astype('datetime64[ns]')
        df = pd.DataFrame(serie,index=dfc_cut.index)
        dfc_cut = dfc_cut[['code_station','resultat_obs_elab','grandeur_hydro_elab','libelle_statut','geometry']]
        dfm = pd.merge(df, dfc_cut, left_index=True, right_index=True)
        dfm.reset_index(drop=True,inplace=True)

        #Vérification de la plage temporelle appelée
        deb = datetime.datetime.strptime(str(period[0]), '%Y')
        fin = datetime.datetime.strptime(str(period[1]), '%Y')  
        
        #Restriction du df aux années appelées
        #if dfm.date_obs_elab.min() <= deb:
            
        #    dfm_cut = dfm.loc[(dfm.date_obs_elab >= deb) & (dfm.date_obs_elab <= fin)]
    
        #Réindexation par date
        dfm_cut = dfm.copy()
        dfm_cut.set_index('date_obs_elab',inplace=True)

        #Grouper par mois avec la moyenne et l'écart-type comme agrégateur

        frames = {
                'date': [],
                'MMF_mean': [],
                'MMF_std': [],
                'code_station': [],
                'geometry': []
                 }
        
        tmp = dfm_cut.groupby(pd.Grouper(freq="M"))['resultat_obs_elab'].mean()
        mean = list(tmp)
        frames['MMF_mean'] = frames['MMF_mean'] + [x for x in mean]
        
        tmp = dfm_cut.groupby(pd.Grouper(freq="M"))['resultat_obs_elab'].std(ddof=1)
        std = list(tmp)
        frames['MMF_std'] = frames['MMF_std'] + [x for x in std]

        #Add the rest of the columns
        #Date
        l = [str(d) for d in list(tmp.index)]
        frames['date'] = frames['date'] + [d[:-9] for d in l]
        #Code station
        code = dfm_cut['code_station'].iloc[0]
        frames['code_station'] = frames['code_station'] + [str(code) for x in range(len(tmp))]
        #Geometry
        geom = dfc_hydro['geometry'].iloc[0]
        frames['geometry'] = frames['geometry'] + [str(geom) for x in range(len(tmp))]
        #Convert to geodataframe and write to disk
        df = pd.DataFrame(frames)
        df['geometry'] = df['geometry'].apply(wkt.loads)
        gdf = gpd.GeoDataFrame(df,geometry='geometry',crs=f"EPSG:{str(epsgCode)}")
        gdf.to_file(dstLayer)

        #else:
        #    pass
    
    else:
        pass

    try:
        gdf
    except:
        pass
    else:
        return gdf





def MannKendallStat(stationCode,srcFile,datesLayerName,valuesLayerName,statistic,generate_plot=False):
    
    """
    stationCode: code of station under analysis [string]
    srcFile: /path/to/source/file.csv where temporal series is stored [string]
    datesLayerName: name of the column containing dates, e.g. "dates" [string] #The date must be structured as yyyy-mm-dd.
    valuesLayerName: name of the column containing values, e.g. "mean montly flows" [string]
    statistic: the statistic that is sampled in series (e.g. "mean" or "std") [string]
    generate_plot: set it to True if the scatter plot of the series + the Sen's slope trend must be plotted in a graph ; otherwise set it to False [default False]
    
    output: tuple (MK Z statistic, Sen's slope, intercept, delta)
    """

    import numpy as np
    import scipy
    import pandas as pd
    import os
    import matplotlib.pyplot as plt
    
    ############
    print("######################### 0th Prepare data")
    #############
    try :
        gdf = pd.read_csv(srcFile)
        
        tmp = gdf.copy()
        #Sort ascending by date
        tmp[f"{datesLayerName}"] = pd.to_datetime(tmp[f"{datesLayerName}"])
        tmp = tmp.sort_values(by=f"{datesLayerName}")
        tmp.reset_index(drop=True, inplace=True)

        dates = list(tmp[f"{datesLayerName}"])
        values = list(tmp[f"{valuesLayerName}"])
    
    except Exception as e:
        raise Exception(f"ERROR in hdrofunc.MannKendallStat, in 0th Prepare data.\n{e}")

    #############
    print("######################### 1st Compute MK regression")
    #############
    try :
        #########
        # MK test
        #########

        #Import time serie and removing NaN values
        
        cc = values.copy()
        j_serie = [x for x in cc if not np.isnan(x)]
        ccc = values.copy()
        k_serie = [x for x in ccc if not np.isnan(x)]
        
        #Computing sign of each differences

        s = []
        Qi = []

        for k in range(len(k_serie)):

            Qj = []

            for j in range(k+1,len(j_serie)):
                tmp = j_serie[j]-k_serie[k]
                if tmp > 0:
                    s.append(1)
                elif tmp == 0:
                    s.append(0)
                else:
                    s.append(-1)
                Qj.append(tmp/(j-k)) #To further compute Sen's slope

            for elem in range(len(Qj)):
                Qi.append(Qj[elem])

        s_sum = np.asarray(s).sum()


        #Computing tied groups

        a_serie = np.asarray(j_serie)
        val, counts = np.unique(a_serie, return_counts=True)

        g = []

        for t in range(len(counts)):

            prod = counts[t]*(counts[t]-1)*(2*counts[t]+5)
            g.append(prod)

        g_sum = np.asarray(g).sum()

        #computing variance of sign as a function of tied groups

        n = len(j_serie)
        var_s = (1/18)*(n*(n-1)*(2*n+5)-g_sum)

        #Compute test statistic Z 

        if s_sum > 0:
            z = (s_sum-1)/np.sqrt(np.asarray(var_s))
        elif s_sum == 0:
            z = 0
        else:
            z = (s_sum+1)/np.sqrt(np.asarray(var_s))
        
        #Compute Sen's slope estimator (see: DOI 10.1007/s11069-015-1644-7)
        Qi_sorted = np.sort(np.asarray(Qi))
        Qis_list = list(Qi_sorted)
        Qi1 = Qis_list[int(np.trunc(len(Qis_list)/2))]
        Qi2 = Qis_list[int(np.trunc((len(Qis_list)+2)/2))]
        slope = (1/2)*(Qi1+Qi2)
        
        #Compute Sen's regression line
        #https://en.wikipedia.org/wiki/Theil%E2%80%93Sen_estimator
        #Line : y = mx + b where m = Sen's slope and b = med(bi) = med(yi - m.xi)
        med = []
        for y in range(len(j_serie)-1):
            p = j_serie[y+1] - slope*y
            med.append(p)

        numeric_med = [float(x) for x in med]
        intercept = np.median(np.asarray(numeric_med))
        
        #delta = flow variation between (i) the estimated flow at strating time in the serie and (ii) estimated flow at ending time in the serie, expressed in % of ((ii)-(i))/(i)
        delta = ((slope*len(j_serie)+intercept) - intercept) / intercept
    
    except Exception as e:
        raise Exception(f"ERROR in hdrofunc.MannKendallStat, in 1st Compute MK regression.\n{e}")
    
    #############
    print("######################### 2nd Draw hypothesis test on z-value")
    #############
    try :
        #Conduct a two-tailed test independent on the sign of z
        #H0: no monotonic trend ; versus H1: monotonic trend

        p_value = 2 * (1 - scipy.stats.norm.cdf(abs(z)))

        oneSideTest = False
        if oneSideTest is True:
        
            if z <= float(0): 
                
                #H0: no monotonic trend ; versus H1: downward monotonic trend
            
                p_value = scipy.stats.norm.cdf(z)
                #Find alpha (significance level) such that H0 is rejected over H1, i.e. alpha | p_value < alpha (alpha such that z_value is significant)
                c = []
                for alpha in np.arange(0.01,0.98,1/100):
                    if p_value < alpha:
                        c.append(alpha)
                    else:
                        pass
                if len(c) != 0:
                    first = c[0]
                    confidence = 1 - first
                else:
                    confidence = 0
        
            else:
        
                #H0: no monotonic trend ; versus H1: upward monotonic trend
                
                p_value = 1 - scipy.stats.norm.cdf(z)
                #Find alpha (significance level) such that H0 is rejected over H1, i.e. alpha | (1-p_value) - alpha < 0 (alpha such that z_value is significant)
                c = []
                for alpha in np.arange(0.01,0.98,1/100):
                    if p_value < alpha:
                        c.append(alpha)
                    else:
                        pass
                if len(c) != 0:
                    first = c[0]
                    confidence = 1 - first
                else:
                    confidence = 0
        else:
            pass

    except Exception as e:
        raise Exception(f"ERROR in hdrofunc.MannKendallStat, in 2nd Draw hypothesis test on z-value.\n{e}")

    ############
    print("######################### 3rd Plot graphs if required")
    ############
    try :
        if generate_plot is True:

            plt.plot(dates, values, 'k-', linewidth=0.5, label=f"MonthlyFlow_{statistic}")
            plt.plot(dates,
                    [slope*x+intercept for x in range(len(values))],
                    'r--',
                    linewidth=1,
                    label=f"Global trend ({str(np.round(delta,decimals=2)*100)}% with a p-value of {str(np.round(p_value,decimals=4))})"
                    )
            plt.xlabel('Time series')
            if statistic == "mean":
                plt.ylabel('Mean Monthly Flow [l.s-1]')
            else:
                plt.ylabel('Monthly Flow Deviation [l.s-1]')
            plt.legend(loc="upper right")
            plt.title(f"Monthly flow variation and linear trend at gauging station {stationCode}") 
            plt.text(0.03, 0.03, '(c) Q. DASSIBAT -- CC BY 4.0', fontsize=5, color='gray', transform=plt.gcf().transFigure)
            plt.savefig(f"./analysis/MannKendallRegression_MMF_{statistic}_station{stationCode}.png",dpi=300)
            #plt.show()
            plt.close()

        else:
            pass
    
    except Exception as e:
        raise Exception(f"ERROR in hdrofunc.MannKendallStat, in 3rd Plot graphs.\n{e}")

    return z, slope, intercept, delta, p_value




def make_map_LabelsOnPoints(srcLayerPolygons,layerNameForPolygons,layerNameForLabels,srcLayerPoints,srcLayerPolygonsNaN,plotTitle,dstFile):

    """
    Makes a map plot to render a geodataframe of polygons. Originally designed to plot results of the Mann-Kendall test. 

    srcLayerPolygons: /path/to/vector/layer.gpkg [string] For catchments with data #Must be a ploygon-geometry geodataframe with geometry column name = 'geometry'
    srcLayerPoints: /path/to/vector/layer.gpkg [string] For outlets #Must be a point-geometry geodataframe with geometry column name = 'geometry'
    srcLayerPolygonsNaN: /path/to/vector/layer.gpkg [string] For catchments with no data #Must be a ploygon-geometry geodataframe with geometry column name = 'geometry'
    layerNameForPolygons: name of the column from which to extract data that will be plotted as polygons [string]
    layerNameForLabels: name of the column from which to extract data that will be plotted as text labels overlapping polygons [string]
    plotTitle: title to give to the plot [string]
    dstFile: /path/to/destination/image.png [string]
    
    output: map with format .png
    """

    import geopandas as gpd
    import matplotlib.pyplot as plt
    from shapely.geometry import Point
    from matplotlib.lines import Line2D
    import contextily as ctx

    # Plot
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    
    # Plot the polygons with data
    gdf = gpd.read_file(srcLayerPolygons)
    gdf = gdf[~gdf.geometry.isnull()]
    gdf.to_crs(3857,inplace=True) #To match contextily default crs for better rendering
    gdf.plot(column=layerNameForPolygons, ax=ax, legend=True, cmap='viridis', alpha=0.7, edgecolor=(0, 0, 0, 0.5), linewidth=0.7)

    # Plot the polygons without data
    #list_NoNaN_stations = list(set(gdf['code_station']))
    gdf_catchAll = gpd.read_file(srcLayerPolygonsNaN)
    #gdf_catchNaN = gdf_catchAll.loc[~gdf_catchAll['code_station'].isin(list_NoNaN_stations)]
    #gdf_catchNaN = gdf_catchNaN.loc[~gdf_catchNaN.geometry.isnull()]
    gdf_catchAll = gdf_catchAll.loc[~gdf_catchAll.geometry.isnull()]
    gdf_catchAll.to_crs(3857,inplace=True) #To match contextily default crs for better rendering
    gdf_catchAll.plot(ax=ax, facecolor='none',edgecolor='red', linestyle='--', linewidth=0.7)
    #gdf_catchNaN.plot(ax=ax,edgecolor=(0, 0, 0, 0.5), linewidth=0.5)

    # Plot the points
    gdf_points = gpd.read_file(srcLayerPoints)
    gdf_points = gdf_points[~gdf_points.geometry.isnull()]
    gdf_points.to_crs(3857,inplace=True)
    gdf_points.plot(ax=ax,marker='o', markersize=5,color='black')

    #Add labels
    gdf_points[f"{layerNameForLabels}_round"] = gdf_points[layerNameForLabels].round(4)
    for x, y, label in zip(gdf_points.geometry.x, gdf_points.geometry.y, gdf_points[f"{layerNameForLabels}_round"]):
        ax.text(x, y, label, fontsize=5, ha='right')
    
    
    # Add labels using the 'name' column
    ##Round values to 2-decimal precision
    #gdf[f"{layerNameForLabels}_round"] = gdf[layerNameForLabels].round(2)
    ##Plot
    #for idx, row in gdf.iterrows():
        # Get the centroid of the polygon
        #centroid = row['geometry'].centroid
        # Ensure the centroid is within the polygon, otherwise find a better point
        #if not row['geometry'].contains(centroid):
        #centroid = row['geometry'].representative_point()
        # Place the label at the centroid or representative point
        #ax.text(centroid.x, centroid.y, row[f"{layerNameForLabels}_round"], fontsize=10, ha='center', va='center', color='black')
    
    # Add a title and labels (optional)
    ax.set_title(plotTitle, pad=5, fontsize=10)
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    plt.tight_layout()
    plt.subplots_adjust(top=0.95)
    fig.text(0.05, 0.05, '(c) Q. DASSIBAT -- CC BY 4.0', fontsize=7, color='gray', va='bottom', ha='left')

    #Add legend
    #label_legend = Line2D([0], [0], marker='o', color='w', label='confidence_level',
    #                  markerfacecolor='black', markersize=8)
    #ax.legend(handles=[label_legend], loc='upper left', title='Legend')

    #Add a base map
    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.France,alpha=0.7,crs=gdf.crs.to_string())
    
    # Save the figure as a PNG file
    plt.savefig(dstFile, dpi=300)
    
    # Display the plot (optional)
    #plt.show()
    plt.close()

    return


def make_map_LabelsOnPolygons(srcLayerPolygons,layerNameForPolygons,layerNameForLabels,srcLayerPoints,srcLayerPolygonsNaN,plotTitle,dstFile):

    """
    Makes a map plot to render a geodataframe of polygons. Originally designed to plot results of the Mann-Kendall test. 

    srcLayerPolygons: /path/to/vector/layer.gpkg [string] For catchments with data #Must be a ploygon-geometry geodataframe with geometry column name = 'geometry'
    srcLayerPoints: /path/to/vector/layer.gpkg [string] For outlets #Must be a point-geometry geodataframe with geometry column name = 'geometry'
    srcLayerPolygonsNaN: /path/to/vector/layer.gpkg [string] For catchments with no data #Must be a ploygon-geometry geodataframe with geometry column name = 'geometry'
    layerNameForPolygons: name of the column from which to extract data that will be plotted as polygons [string]
    layerNameForLabels: name of the column from which to extract data that will be plotted as text labels overlapping polygons [string]
    plotTitle: title to give to the plot [string]
    dstFile: /path/to/destination/image.png [string]
    
    output: map with format .png
    """

    import geopandas as gpd
    import matplotlib.pyplot as plt
    from shapely.geometry import Point
    from matplotlib.lines import Line2D
    import contextily as ctx

    # Plot
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    
    # Plot the polygons with data
    gdf = gpd.read_file(srcLayerPolygons)
    gdf = gdf[~gdf.geometry.isnull()]
    gdf.to_crs(3857,inplace=True) #To match contextily default crs for better rendering
    gdf.plot(column=layerNameForPolygons, ax=ax, legend=True, cmap='viridis', alpha=0.7, edgecolor=(0, 0, 0, 0.5), linewidth=0.7)

    # Plot the polygons without data
    #list_NoNaN_stations = list(set(gdf['code_station']))
    gdf_catchAll = gpd.read_file(srcLayerPolygonsNaN)
    #gdf_catchNaN = gdf_catchAll.loc[~gdf_catchAll['code_station'].isin(list_NoNaN_stations)]
    #gdf_catchNaN = gdf_catchNaN.loc[~gdf_catchNaN.geometry.isnull()]
    gdf_catchAll = gdf_catchAll.loc[~gdf_catchAll.geometry.isnull()]
    gdf_catchAll.to_crs(3857,inplace=True) #To match contextily default crs for better rendering
    gdf_catchAll.plot(ax=ax, facecolor='none',edgecolor='red', linestyle='--', linewidth=0.7)
    #gdf_catchNaN.plot(ax=ax,edgecolor=(0, 0, 0, 0.5), linewidth=0.5)

    # Plot the points
    #gdf_points = gpd.read_file(srcLayerPoints)
    #gdf_points = gdf_points[~gdf_points.geometry.isnull()]
    #gdf_points.to_crs(3857,inplace=True)
    #gdf_points.plot(ax=ax,marker='o', markersize=5,color='black')

    #Add labels
    #for x, y, label in zip(gdf_points.geometry.x, gdf_points.geometry.y, gdf_points[layerNameForLabels]):
    #    ax.text(x, y, label, fontsize=9, ha='right')
    
    
    #Add labels using the 'name' column
    ##Round values to 2-decimal precision
    gdf[f"{layerNameForLabels}_round"] = gdf[layerNameForLabels].round(4)
    ##Plot
    for idx, row in gdf.iterrows():
        # Get the centroid of the polygon
        centroid = row['geometry'].centroid
        # Ensure the centroid is within the polygon, otherwise find a better point
        if not row['geometry'].contains(centroid):
            centroid = row['geometry'].representative_point()
        # Place the label at the centroid or representative point
        ax.text(centroid.x, centroid.y, row[f"{layerNameForLabels}_round"], fontsize=7, ha='center', va='center', color='black')
    
    # Add a title and labels (optional)
    ax.set_title(plotTitle, pad=5, fontsize=10)
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    plt.tight_layout()
    plt.subplots_adjust(top=0.95)
    fig.text(0.0, 0.05, '(c) Q. DASSIBAT -- CC BY 4.0', fontsize=7, color='gray', va='bottom', ha='left')

    #Add legend
    #label_legend = Line2D([0], [0], marker='o', color='w', label='confidence_level',
    #                  markerfacecolor='black', markersize=8)
    #ax.legend(handles=[label_legend], loc='upper left', title='Legend')

    #Add a base map
    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.France,alpha=0.7,crs=gdf.crs.to_string())
    
    # Save the figure as a PNG file
    plt.savefig(dstFile, dpi=300)
    
    # Display the plot (optional)
    #plt.show()
    plt.close()

    return



def request_DEM(bbox,srcEPSG,dstFile):

    """
    Makes a request at https://portal.opentopography.org/apidocs/#/Public/getGlobalDem and returns a SRTM 30m DEM for the specified bounding box
    bbox: bounding box formated as "xmin ymin xmax ymax" [string]. bbox can be extracted from vector with extract_Vectorbbox() or from raster with extract_Rasterbbox() functions 
    srcEPSG: EPSG code of srcFile [int] The function then converts projection to WGS84 to make the request and then reproject the output back to srcEPSG
    dstFile: /path/to/destination/file.tif [string] Path where the request's output is being written to disk
    
    output: DEM downloaded .tif file reprojected to srcESPG
    """

    import pyproj
    import os
    import requests

    #Read coordinates and reproject them to WGS84 (EPSG 4326)
    bbox_list = bbox.split() #xmin ymin xmax ymax
    transformer = pyproj.Transformer.from_crs(f"EPSG:{str(srcEPSG)}", "EPSG:4326")
    xmin, ymin = transformer.transform(bbox_list[0], bbox_list[1])
    xmax, ymax = transformer.transform(bbox_list[2], bbox_list[3])
    

    #Make the request to opentopography API
    url = f"https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&south={str(ymin)}6&north={str(ymax)}&west={str(xmin)}&east={str(xmax)}&outputFormat=GTiff&API_Key=8aea7de3cd2f16fbdcfcc819216f5eb4"
    print(url)
    r = requests.get(url, allow_redirects=True)
    with open(f"{dstFile[:-4]}_wgs84.tif", "wb") as f:
        f.write(r.content)

    #Reproject tif file to srcEPSG
    src = f"{dstFile[:-4]}_wgs84.tif"
    dst = dstFile
    cmd = f"gdalwarp -overwrite -s_srs EPSG:4326 -t_srs EPSG:{str(srcEPSG)} -r near -of GTiff {src} {dst}"
    os.system(cmd)
    os.remove(f"{dstFile[:-4]}_wgs84.tif")

    return


def split_singleband(srcFile,epsgCode,zRestriction=None):

    """
    Creates a raster .tif scalar file for each pixel value in the single band raster srcFile. Pixel values must be id-like. 
    srcFile: /path/to/source/raster/file.tif
    zRestriction [optional]: list of pixel values to be processed in the srcFile zField [list]
    dstFile follows the geoTransform propreties of srcFile and has path f"{srcFile[:-4]}_PixelValueIs{#}.tif"
    """

    #Import libraries
    
    import numpy as np
    from osgeo import gdal, osr
    gdal.UseExceptions()

    gdalDataTypes = {
                      "uint8": 1,
                      "int8": 1,
                      "uint16": 2,
                      "int16": 3,
                      "uint32": 4,
                      "int32": 5,
                      "float32": 6,
                      "float64": 7,
                      "complex64": 10,
                      "complex128": 11
                    } #see: https://borealperspectives.org/2014/01/16/data-type-mapping-when-using-pythongdal-to-write-numpy-arrays-to-geotiff/

    #Read srcFile and extract info
    
    r = gdal.Open(srcFile)
    band = r.GetRasterBand(1)
    src = band.ReadAsArray().astype(float)
    
    ulx, xres, xskew, uly, yskew, yres = r.GetGeoTransform()
    geoT = r.GetGeoTransform()
    
    h,w = src.shape

    max = band.GetMaximum()

    r = None


    #Iterate over each each pixel value in srcFile and create a separate dstFile for each value

    if zRestriction is None:

        for val in range(int(max)+1):
    
            print(f"Pixel value {str(val)} out of {str(max)}")
        
            #Create an empty array populated with NaN values to further store results
            
            array = np.empty([h,w])
            array[:] = np.float32(np.nan)
        
            #Range over cells and retrieve cells on condition
        
            for y in range(h): 
        
                if y == 0: #yres is negative and y axis goes x-wise
                    ymax = uly 
                    ymin = uly + yres
                else:
                    ymax = uly + y * yres #for last iteration, h = h-1 because of range() behavior
                    ymin = uly + y * yres + yres 
                
                for x in range(w):
        
                    if x == 0:
                        xmin = ulx 
                        xmax = ulx + xres
                    else:
                        xmin = ulx + x * xres 
                        xmax = ulx + x * xres + xres
        
                    if (xmin >= xmax) | (ymin >= ymax):
                        print("Error (x,y)",(x,y))
                    else:
                        pass
        
                    #Set float values
                    current_pixel = np.float32(src[y,x])
                    target_pixel = np.float32(val)
                
        
                    #Retieve pixel on condition
                    if current_pixel == target_pixel:
                        array[y,x] = current_pixel 
                    else:
                        array[y,x] = np.float32(np.nan)
                
            #Export array as dstFile .tif
    
            dstFile = f"{srcFile[:-4]}_PixelValueIs{str(val)}.tif"
            gdalType = gdalDataTypes[array.dtype.name]
            outDs = gdal.GetDriverByName('GTiff').Create(dstFile, w, h, 1, gdalType)
            outBand = outDs.GetRasterBand(1)
            outBand.WriteArray(array)
            outDs.SetGeoTransform(geoT)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(epsgCode)
            outDs.SetProjection(srs.ExportToWkt())
            outDs = None

    else:

        for val in list(zRestriction):
    
            print(f"Pixel value {str(val)} in {str(zRestriction)}")
        
            #Create an empty array populated with NaN values to further store results
            
            array = np.empty([h,w])
            array[:] = np.float32(np.nan)
        
            #Range over cells and retrieve cells on condition
        
            for y in range(h): 
        
                if y == 0: #yres is negative and y axis goes x-wise
                    ymax = uly 
                    ymin = uly + yres
                else:
                    ymax = uly + y * yres #for last iteration, h = h-1 because of range() behavior
                    ymin = uly + y * yres + yres 
                
                for x in range(w):
        
                    if x == 0:
                        xmin = ulx 
                        xmax = ulx + xres
                    else:
                        xmin = ulx + x * xres 
                        xmax = ulx + x * xres + xres
        
                    if (xmin >= xmax) | (ymin >= ymax):
                        print("Error (x,y)",(x,y))
                    else:
                        pass
        
                    #Set float values
                    current_pixel = np.float32(src[y,x])
                    target_pixel = np.float32(val)
                
        
                    #Retieve pixel on condition
                    if current_pixel == target_pixel:
                        array[y,x] = current_pixel 
                    else:
                        array[y,x] = np.float32(np.nan)
                
            #Export array as dstFile .tif
    
            dstFile = f"{srcFile[:-4]}_PixelValueIs{str(val)}.tif"
            gdalType = gdalDataTypes[array.dtype.name]
            outDs = gdal.GetDriverByName('GTiff').Create(dstFile, w, h, 1, gdalType)
            outBand = outDs.GetRasterBand(1)
            outBand.WriteArray(array)
            outDs.SetGeoTransform(geoT)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(epsgCode)
            outDs.SetProjection(srs.ExportToWkt())
            outDs = None

    return max



def raster_to_polygons(srcFile,dstFile,epsgCode,zName,zRestriction=None):

    """
    Converts raster to polygons with one polygon for a connected region of same pixel value
    This function makes a shadow call to relio.split_singleband() to first create one unique raster for each pixel value in srcFile
    Then it builds temporary polygon vector files and then it puts them together in a geodataframe written to disk as dstFile
    srcFile: /path/to/source/raster/file.tif which must contain a unique pixel value and other pixels = NoData: see function relio.split_singleband() [string]
    dstFile: /path/to/destination/vector/file.gpkg which contains the polygons associated with srcFile [string]
    zName: name of the z value field to be given as a layer in dstFile [string]
    zRestriction [optional]: pass a list of values to lighten domain and to process only these values in zName [list]
    """

    #Import libraries
    
    from osgeo import gdal, osr
    gdal.UseExceptions()
    import geopandas as gpd
    import pandas as pd
    import os
    import shutil
    import subprocess
    import sys

    gdal_polygonize_path = shutil.which("gdal_polygonize.py") or shutil.which("gdal_polygonize")
    if gdal_polygonize_path is None:
        raise FileNotFoundError("gdal_polygonize.py was not found in PATH.")
    gdal_polygonize_cmd = [sys.executable, gdal_polygonize_path] if gdal_polygonize_path.endswith(".py") else [gdal_polygonize_path]

    #Call function relio.split_singleband() to split srcFile raster into multiple rasters with unique pixel value
    max = split_singleband(srcFile,epsgCode,zRestriction) #dstFile = f"{srcFile[:-4]}_PixelValueIs{#}.tif"

    #For each above created raster call gdal_polygonize.py

    vectorList =[]

    if zRestriction is None:
    
        for val in range(1,int(max)+1): #catchment=0 is a "fake" catchment generated by pcraster.subcatchment(), so forget it

            rasterFile = os.path.normpath(rf"{srcFile[:-4]}_PixelValueIs{str(val)}.tif")
            tmpVectorFile = os.path.normpath(rf"{srcFile[:-4]}_PixelValueIs{str(val)}.gpkg")
            cmd = gdal_polygonize_cmd + [rasterFile, "-overwrite", "-b", "1", "-f", "GPKG", tmpVectorFile, "OUTPUT", zName]
            subprocess.run(cmd, check=True)
            #The above gdal command returns a vector file with multiple entities: one polygon for the envelop, and multiple polygons where region is broken
            #So we remove the envelop (catch_id=0) polygon mnd merge the others 
            tmpVectorLoad = gpd.read_file(tmpVectorFile)
            tmpVectorLoad[f"{zName}"] = tmpVectorLoad[f"{zName}"].astype("string")
            m = tmpVectorLoad[f"{zName}"] == str(val)
            tmpVectorLoadCleared = tmpVectorLoad.loc[m] #returns a gdf without catch_id=0
            union = tmpVectorLoadCleared.unary_union #returns a shapely.geometry
            frames = {'catch_id':[val],
              'geometry' : [union]}
            uniongdf = gpd.GeoDataFrame(frames, crs=f"EPSG:{str(epsgCode)}")
            uniongdf = uniongdf.set_geometry('geometry')
            if os.path.exists(dstFile):
                os.remove(tmpVectorFile)
                uniongdf.to_file(tmpVectorFile)
            else:
                uniongdf.to_file(tmpVectorFile)
            vectorList.append(uniongdf)
            del rasterFile, tmpVectorFile, tmpVectorLoad, tmpVectorLoadCleared, union, uniongdf
    
        #Concatenate each above creater vector layers into a single geodatframe
        df = pd.concat(vectorList)
        gdf = gpd.GeoDataFrame(df, crs=f"EPSG:{str(epsgCode)}")
        gdf = gdf.set_geometry('geometry')
        #Drop NonType geometries
        gdfNoNull = gdf[~gdf.geometry.isnull()]
    
        #Write geodataframe to disk
        if os.path.exists(dstFile):
            os.remove(dstFile)
            gdfNoNull.to_file(dstFile)
        else:
            gdfNoNull.to_file(dstFile)
    

    else:

        for val in list(zRestriction): #catchment=0 is a "fake" catchment generated by pcraster.subcatchment(), so forget it
    
            rasterFile = os.path.normpath(rf"{srcFile[:-4]}_PixelValueIs{str(val)}.tif")
            tmpVectorFile = os.path.normpath(rf"{srcFile[:-4]}_PixelValueIs{str(val)}.gpkg")
            cmd = gdal_polygonize_cmd + [rasterFile, "-overwrite", "-b", "1", "-f", "GPKG", tmpVectorFile, "OUTPUT", zName]
            subprocess.run(cmd, check=True)
            #The above gdal command returns a vector file with multiple entities: one polygon for the envelop, and multiple polygons where region is broken
            #So we remove the envelop (catch_id=0) polygon mnd merge the others 
            tmpVectorLoad = gpd.read_file(tmpVectorFile)
            tmpVectorLoad[f"{zName}"] = tmpVectorLoad[f"{zName}"].astype("string")
            m = tmpVectorLoad[f"{zName}"] == str(val)
            tmpVectorLoadCleared = tmpVectorLoad.loc[m] #returns a gdf without catch_id=0
            union = tmpVectorLoadCleared.unary_union #returns a shapely.geometry
            frames = {'catch_id':[val],
              'geometry' : [union]}
            uniongdf = gpd.GeoDataFrame(frames, crs=f"EPSG:{str(epsgCode)}")
            uniongdf = uniongdf.set_geometry('geometry')
            if os.path.exists(dstFile):
                os.remove(tmpVectorFile)
                uniongdf.to_file(tmpVectorFile)
            else:
                uniongdf.to_file(tmpVectorFile)
            vectorList.append(uniongdf)
            del rasterFile, tmpVectorFile, tmpVectorLoad, tmpVectorLoadCleared, union, uniongdf
    
        #Concatenate each above creater vector layers into a single geodatframe
        df = pd.concat(vectorList)
        gdf = gpd.GeoDataFrame(df, crs=f"EPSG:{str(epsgCode)}")
        gdf = gdf.set_geometry('geometry')
    
        #Write geodataframe to disk
        if os.path.exists(dstFile):
            os.remove(dstFile)
            gdf.to_file(dstFile)
        else:
            gdf.to_file(dstFile)
    
   
    return


def convert_to_pcraster(srcFile,dstFile,epsgCode,maskFile):

    """
    Convert continuous .tif raster to a scalar .map raster

    maskFile : path/to/mask/raster/file.tif used to retrieve a geoTransform and set proper bbox to the PCRatser file
    """

    import os
    from osgeo import gdal, gdalconst
    gdal.UseExceptions()

    #Read maskfile to get geotransfrom info
    mask = gdal.Open(maskFile)
    upx, xres, xskew, upy, yskew, yres = mask.GetGeoTransform()
    cols = mask.RasterXSize
    rows = mask.RasterYSize
     
    ulx = upx + 0*xres + 0*xskew
    uly = upy + 0*yskew + 0*yres
     
    llx = upx + 0*xres + rows*xskew
    lly = upy + 0*yskew + rows*yres
     
    lrx = upx + cols*xres + rows*xskew
    lry = upy + cols*yskew + rows*yres

    #Set gdal options
    ot = gdalconst.GDT_Float32
    mtdOptions = "VS_SCALAR"
    
    #GDAL Translate
    cmd = f"gdal_translate -a_srs EPSG:{str(epsgCode)} -a_ullr {str(ulx)} {str(uly)} {str(lrx)} {str(lry)} -ot Float32 -of PCRaster {str(srcFile)} {str(dstFile)}"
    os.system(cmd)
    #Note: still with a proper geoTransform options setting, .tif and .map rasters do not exactly overlap...
    
    #Properly close the datasets to flush to disk
    del mask

    return




def create_flowdirection(srcFile, dstFile, cloneFile, outflowdepth, corevolume, corearea, catchmentprecipitation):

    """
    Remove pits from a DEM raster (prior conversion to PCRaster format is required) through generating a FlowDirection map
    Parameters to remove pits (when the cell under consideration is higher than the 4 values, it is considered a pit and not removed) 
    So to remove all pits set very high value e.g. 1e31
    
    cloneFile: Only the PCRaster file format is supported as input argument
    """ 

    from pcraster import readmap, setclone, lddcreate, report
    import os
    #import importlib
    #importlib.invalidate_caches()

    #Create clone map 
    setclone(cloneFile)

    #Create flow direction map
    dem = readmap(srcFile)
    flowDirection = lddcreate(dem,outflowdepth,corevolume,corearea,catchmentprecipitation)
    report(flowDirection,dstFile)

    #Close variables
    dem = None
    flowDirection = None

    return
    

def create_subcatchments(outletsLayer,flowdirectionRaster,dstRaster,cloneMap):
    
    """
    outletsLayer: /path/to/point/vector/layer.gpkg or any compatible format with geopandas drivers, must be point geometry [string]
    flowdirectionRaster: /path/to/flowdirection/raster.map [string]
    cloneMap: /path/to/pcraster/clone.map [string]
    
    dstRaster: /path/to/destination/raster.map where subcatchments appear on the same raster with one pixel value for each [string]
    """
    
    import geopandas as gpd
    import os
    from pcraster import readmap, subcatchment, report
    wd = os.getcwd()
    #import gc
    #gc.collect()
    
    #Convert .gpkg outletsLayer to .txt file with structure: x_coord y_coord id
    
    gdf = gpd.read_file(outletsLayer)
    coords_wkt = list(gdf['geometry'])
    coords_string = [str(x) for x in coords_wkt]
    coords_export = []
    idx = 0
    for elem in coords_string:
        tmp = elem[6:]
        coords_split = tmp.split(" ")
        xcoord = coords_split[0][1:]
        ycoord = coords_split[1][:-1]
        if idx != len(coords_string)-1:
            coords_export.append(f"{str(xcoord)}"+" "+f"{str(ycoord)}"+" "+f"{str(idx+1)}"+"\n")
        else:
            coords_export.append(f"{str(xcoord)}"+" "+f"{str(ycoord)}"+" "+f"{str(idx+1)}")
        idx += 1
    
    txtFile = f"{wd}/tmp_outlets.txt"
    if os.path.isfile(txtFile) is True:
        os.remove(txtFile)
    else:
        pass
    f = open(txtFile,"w+")
    f.writelines(coords_export)
    f.close()
    
    
    #Convert .txt file to .map PCRaster file
    
    dst = f"./tmp/tmp_outlets_pcraster.map"
    if os.path.isfile(dst) is True:
        os.remove(dst)
    else:
        pass
    cmd = f"col2map --clone {cloneMap} -N {txtFile} {dst}"
    print(cmd)
    os.system(cmd)
    os.remove(txtFile)
    
    #Generate catchments map with FlowDirection map and Outlet map 

    #FlowDirection = readmap(flowdirectionRaster)
    #OutletMap = readmap(dst)
    Catch = subcatchment(flowdirectionRaster,dst)
    report(Catch,f"{dstRaster}")
    
    #Flush memory 
    #os.remove(txtFile)
    #os.remove(dst)
    FlowDirection = None
    OutletMap = None
    Catch = None
    cloneMap = None
    
    
    return


def create_material(maskFile,dstFile,epsgCode,materialValue,initialConditionsArray=None):
    
    """
    Creates a raster .tif scalar file with every cell equals to materialValue and with geo properties equals to maskFile
    Usefull to generate a material map, which together with a flow direction map, are used to derive an accuflux map 

    initialConditionsArray [optional] : numpy.array of shape (nb_rows,2) with each element [initial_accuflux,index].
    It must be indexed on a same-shape raster as mskFile
    """

    import numpy as np
    from osgeo import gdal, osr
    gdal.UseExceptions()
    gdalDataTypes = {
              "uint8": 1,
              "int8": 1,
              "uint16": 2,
              "int16": 3,
              "uint32": 4,
              "int32": 5,
              "float32": 6,
              "float64": 7,
              "complex64": 10,
              "complex128": 11
            } #see: https://borealperspectives.org/2014/01/16/data-type-mapping-when-using-pythongdal-to-write-numpy-arrays-to-geotiff/

    #Read maskfile to get geotransfrom info
    
    r = gdal.Open(maskFile)
    band = r.GetRasterBand(1)
    a = band.ReadAsArray().astype(float)
    ulx, xres, xskew, uly, yskew, yres = r.GetGeoTransform()
    nrows, ncols = a.shape
    geoT = r.GetGeoTransform()

    #Generate numpy array with value = materialValue and properties = maskFile
    
    materialArray = np.full(a.shape,np.float32(materialValue))

    #Apply optional initialConitionsArray

    if initialConditionsArray is None:

        pass

    else:

        conditionsArray = np.array(initialConditionsArray)
        
        #Generate the correspondance matrix between pixel index in raster maskFile and array
        
        index_matrix = np.empty([nrows,ncols])
        index_matrix[:] = np.float32(np.nan)
        index = 0
    
        for y in range(nrows): 
            if y == 0: #yres is negative and y axis goes x-wise
                ymax = uly 
                ymin = uly + yres
            else:
                ymax = uly + y * yres #for last iteration, h = h-1 because of range() behavior
                ymin = uly + y * yres + yres 
            for x in range(ncols):
                if x == 0:
                    xmin = ulx 
                    xmax = ulx + xres
                else:
                    xmin = ulx + x * xres 
                    xmax = ulx + x * xres + xres
                if (xmin >= xmax) | (ymin >= ymax):
                    print("Error (x,y)",(x,y))
                else:
                    pass
                
                index_matrix[y,x] = np.int32(index)
                index += 1

        #Modify materialArray with initialConditionsArray based on index_matrix

        index = 0
        h,w = conditionsArray.shape

        #Range over elements in materialArray
        for y in range(nrows):
            
            for x in range(ncols):

                #Find matching index in initialConditionsArray if any and change corresponding materialValue accordingly
                for row in range(h):
                    
                    i = conditionsArray[row,1]
                    
                    if np.int32(i) == np.int32(index):

                        initialValue = np.float32(conditionsArray[row,0])
                        materialArray[y,x] = initialValue

                    else:
                        pass
                        
                index += 1

    #Export array as dstFile .tif

    gdalType = gdalDataTypes[materialArray.dtype.name]
    outDs = gdal.GetDriverByName('GTiff').Create(dstFile, ncols, nrows, 1, gdalType)
    outBand = outDs.GetRasterBand(1)
    outBand.WriteArray(materialArray)
    outDs.SetGeoTransform(geoT)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsgCode)
    outDs.SetProjection(srs.ExportToWkt())
    outDs = None

    return



def create_accuflux(flowDirection, material, dstFile, cloneFile):

    """
    Creates accuflux .map based on flowDirection .map and material .map

    cloneFile: Only the PCRaster file format is supported as input argument
    """ 

    from pcraster import setclone, readmap, accuflux, report
    #import gc
    #gc.collect()
    #import importlib
    #importlib.invalidate_caches()

    #Create clone map 
    setclone(cloneFile)

    #Create accuflux map
    flowdir = readmap(flowDirection)
    mat = readmap(material)
    acc = accuflux(flowdir,mat)
    report(acc,dstFile)

    #Close variables
    del flowdir
    del mat
    del acc

    return


def extract_cellsValues(srcFile,*dropna):
    
    """
    srcFile: path/to/source/raster/file.tif [string]
    dropna [optional]: if set to True, the returned dict will not include cells with NaN values [Python object]
    output : python dictionary with keys 'coordinates', 'values', 'id' i.e. 'coordinates':["xmin ymin xmax ymax", ...], 'value':[...], 'id':[(y,x),...] for each cell in srcFile [dict]
    """
    
    from osgeo import gdal
    gdal.UseExceptions()
    import numpy as np
    
    r = gdal.Open(srcFile)
    band = r.GetRasterBand(1)
    a = band.ReadAsArray().astype(float)
    
    ulx, xres, xskew, uly, yskew, yres = r.GetGeoTransform()
    
    h,w = a.shape
    
    coords = []

    #Create empty dictionary to further store results
    
    frames = {'coordinates':[],
              'values':[],
             'id':[]}
    
    for y in range(h): 

        if y == 0: #yres is negative and y axis goes x-wise
            ymax = uly 
            ymin = uly + yres
        else:
            ymax = uly + y * yres #for last iteration, h = h-1 because of range() behavior
            ymin = uly + y * yres + yres 
        
        for x in range(w):

            if x == 0:
                xmin = ulx 
                xmax = ulx + xres
            else:
                xmin = ulx + x * xres 
                xmax = ulx + x * xres + xres

            if (xmin >= xmax) | (ymin >= ymax):
                print("Error (x,y)",(x,y))
            else:
                pass

            if dropna is True:
            
                if np.float32(a[y,x]) == np.float32(np.nan):
                    pass
                else:
                    frames['coordinates'].append(f"{xmin} {ymin} {xmax} {ymax}")
                    frames['values'].append(np.float32(a[y,x])) #numpy default float format is float64 which is not compatible with pandas.df float32 format (for further uses)
                    frames['id'].append((y,x))
            
            else:
                frames['coordinates'].append(f"{xmin} {ymin} {xmax} {ymax}")
                frames['values'].append(np.float32(a[y,x]))
                frames['id'].append((y,x))
    
    r = None
    
    return frames


def count_tiedCells(srcFile,valuesList):
    
    """
    Counts the number of pixels equal to each value in valuesList, i.e. for each tied group in the raster, the number of pixels of each group
    srcFile: path/to/source/raster/file.tif [string]
    valuesList: list of values that will be checked [list]
    output : python dictionary with keys 'tiedValue', 'tiedCount' [dict]
    """
    
    from osgeo import gdal
    gdal.UseExceptions()
    import numpy as np
    
    r = gdal.Open(srcFile)
    band = r.GetRasterBand(1)
    a = band.ReadAsArray().astype(float)
    
    ulx, xres, xskew, uly, yskew, yres = r.GetGeoTransform()
    
    h,w = a.shape

    #Create empty dictionary to further store results
    
    frames = {'tiedValue':[],
              'tiedCount':[]}
    
    for val in valuesList:

        count = 0
    
        for y in range(h): 
    
            if y == 0: #yres is negative and y axis goes x-wise
                ymax = uly 
                ymin = uly + yres
            else:
                ymax = uly + y * yres #for last iteration, h = h-1 because of range() behavior
                ymin = uly + y * yres + yres 
            
            for x in range(w):
    
                if x == 0:
                    xmin = ulx 
                    xmax = ulx + xres
                else:
                    xmin = ulx + x * xres 
                    xmax = ulx + x * xres + xres
    
                if (xmin >= xmax) | (ymin >= ymax):
                    print("Error (x,y)",(x,y))
                else:
                    pass
    
                pixel = np.float32(a[y,x])
                if pixel == np.float32(val):
                    count += 1
                else:
                    pass

        
        frames['tiedValue'].append(val)
        frames['tiedCount'].append(count)
        del count, val

    r = None
    
    return frames



def cells_to_points(dictCells,epsgCode,*dstFile):

    """
    dictCells: python dictionary containing keys 'coordinates' and 'values' i.e. 'coordinates':["xmin ymin xmax ymax", ...], 'value':[...] [dict]
    dstFile [optional]: /path/to/vector/layer.gpkg [string]

    output: geodataframe with cells turned to points through centroid [geopandas.DataFrame]
    """

    #Import libraries
    
    import pandas as pd
    from shapely.geometry import Point
    import geopandas as gpd

    #Convert dictCells to dataframe

    df = pd.DataFrame(dictCells)
    df['coordinates'] = df['coordinates'].astype('string')
    listCoordinates = list(df['coordinates'])
    listxmin = []
    listxmax = []
    listymin = []
    listymax = []
    for elem in listCoordinates:
        tmp = elem.split(" ")
        listxmin.append(tmp[0])
        listymin.append(tmp[1])
        listxmax.append(tmp[2])
        listymax.append(tmp[3])
    df['xmin'] = listxmin
    df['ymin'] = listymin
    df['xmax'] = listxmax
    df['ymax'] = listymax
    
    #Create columns for center x coord and center y coord"
    
    df['xmin'] = df['xmin'].astype('float')
    df['xmax'] = df['xmax'].astype('float')
    df['ymin'] = df['ymin'].astype('float')
    df['ymax'] = df['ymax'].astype('float')
    df['xcenter'] = (df['xmin'] + df['xmax']) / 2
    df['ycenter'] = (df['ymin'] + df['ymax']) / 2
    
    #Drop useless colmumns
    
    fields = ['values','xcenter','ycenter']
    dfc = df[fields]

    df = None

    #Reset index
    
    dfc = dfc.reset_index()

    #Convert dataframe to geodataframe
    
    geometry = [Point(xy) for xy in zip(dfc['xcenter'], dfc['ycenter'])]
    tmp = dfc.drop(['xcenter', 'ycenter','index'], axis=1)
    gdf = gpd.GeoDataFrame(tmp, crs=f"EPSG:{str(epsgCode)}", geometry=geometry)

    tmp = None
    dfc = None
    
    #Optionnaly export to vector layer (format GPKG)

    if len(dstFile) != 0:
        gdf.to_file(dstFile)
    else:
        pass

    
    return gdf


def sjoin_nearest_unique(left_df, right_df, left_suffix, right_suffix):

    """
    Designed to prevent sjoin_nearest() function of geopandas to join several entities in left_df to one entity in right_df.
    The result is a geodataframe where each point in left_df is matched to a unique nearest point in right_df without losing any entities. 
    """

    import geopandas as gpd
    
    # Copy of the right_df to keep track of available points
    available_right_df = right_df.copy()
    
    # List to store the result
    result = []

    for left_point in left_df.itertuples():
        # Find the nearest available right point
        distances = available_right_df.geometry.apply(lambda x: left_point.geometry.distance(x))
        nearest_index = distances.idxmin()
        
        # Append the left point and its nearest right point to the result
        result.append((left_point.Index, nearest_index))
        
        # Remove the assigned right point from the available points
        available_right_df = available_right_df.drop(index=nearest_index)
        
    # Create a DataFrame from the result
    result_df = gpd.GeoDataFrame(result, columns=['left_index', 'right_index'])
    
    # Merge the left and right GeoDataFrames on their indices
    merged_df = left_df.merge(result_df, left_index=True, right_on='left_index')
    merged_df = merged_df.merge(right_df, left_on='right_index', right_index=True, suffixes=(f"_{left_suffix}", f"_{right_suffix}"))
    
    return merged_df


def join_points_to_pixels(pointsFile,pointsLayer,rasterFile,epsgCode,dstFile):
    
    """
    Originally made to extract resampled discharge values based on their nearest position to gauge stations.
    Returns a geodataframe where geometry is the one of the closest-to-stations pixels and attributes are from both source files
    Makes a shadow call to functions extract_cellsValues() and cells_to_points()
    
    pointsFile: /path/to/vector/points/file.gpkg [string]
    pointsLayer: name of the column in pointsFile that will be retrieved in output [string]
    rasterFile: /path/to/raster/file.tif [string]
    epsgCode: EPSG Code of both pointsFile and rasterFile [int]
    
    dstFile: /path/to/destination/file.gpkg that is the point geometry geodataframe with merged attributes and coordinates taken from rasterFile's pixels [string]       
    """
    
    import geopandas as gpd
    import pandas as pd
    from shapely import wkt
    import numpy as np
    
    #Convert rasterFile to geoDataFrame and create a 'uid' column
    raster = extract_cellsValues(rasterFile)
    gdf_raster = cells_to_points(raster,epsgCode)
    uids  = [i for i in range(len(gdf_raster))]
    gdf_raster.loc[:,'id_pixel'] = uids
    
    #Exclude NaN values from gdf_raster
    gdf_raster.dropna(axis=0,subset='values',inplace=True)
    
    #Open pointsFile and cut dataframe to only the following columns ['pointsLayer','geometry','code_station'] 
    points = gpd.read_file(pointsFile)
    gdf_points = points[[f"{str(pointsLayer)}",'geometry','code_station']]
    uids = [i for i in range(len(gdf_points))]
    gdf_points.loc[:,'id_point'] = uids

    #Greedy spatial join 
    
    distance_matrix = gdf_points.geometry.apply(lambda g: gdf_raster.distance(g))

    frames = {'id_point': [],
             'id_pixel': []}

    for row in range(len(distance_matrix)):

        min_col = distance_matrix.loc[row].idxmin()
        frames['id_pixel'].append(str(min_col))
        frames['id_point'].append(str(row))
        distance_matrix.drop(min_col,axis=1,inplace=True)

    join = pd.DataFrame(frames)
    join_ids = [i for i in range(len(join))]
    join.loc[:,'id_join'] = join_ids
                                           
    #Retrieve attributes of each former df
    gdf_raster_geom = gdf_raster[['geometry','id_pixel']]
    join['id_pixel'] = join['id_pixel'].astype("string")
    gdf_raster_geom['id_pixel'] = gdf_raster_geom['id_pixel'].astype("string")
    merge_raster = join.merge(gdf_raster_geom,left_on='id_pixel',right_on='id_pixel',how='left')

    gdf_points_nogeom = gdf_points[[f"{str(pointsLayer)}",'code_station','id_point']]
    join['id_point'] = join['id_point'].astype("string")
    gdf_points_nogeom['id_point'] = gdf_points_nogeom['id_point'].astype("string")
    merge_points = join.merge(gdf_points_nogeom,left_on='id_point',right_on='id_point',how='left')

    merge_final = merge_raster.merge(merge_points,left_on='id_join',right_on='id_join',how='left')
    
    #Build geodataframe
    gdf = gpd.GeoDataFrame(merge_final, crs=f"EPSG:{str(epsgCode)}", geometry='geometry')
    
    #Write gdf to disk
    gdf.to_file(dstFile)  
    
    return gdf



def convert_to_geotiff(srcFile,dstFile,epsgCode):

    """
    Convert scalar .map raster to a contiuous .tif raster
    """

    from osgeo import gdal
    gdal.UseExceptions()
    import os

    #GDAL Translate
    cmd = f"gdal_translate -a_srs EPSG:{str(epsgCode)} -of GTiff {str(srcFile)} {str(dstFile)}"
    os.system(cmd)

    return


def clip_to_shapefile(srcFile,dstFile,EPSG,maskFile):

    """
    srcFile: path/to/source/raster/file.tif [string]
    dstFile: path/to/destination/raster/file.tif [string]
    maskFile: path/to/mask/raster/file.gpkg or any osgeo-compatible vector format [string] WARNING if the extension is not of length 4, code needs to be modified to match the length of the actual file extension, e.g. len("shp") = 3 but len('gpkg') = 4
    EPSG: epsg code of both src, mask and dst (must be the same) [int]
    """

    import os
    import numpy as np

    #Extract layerName from maskFile
    a = maskFile
    b = np.char.split(a, sep ='/') 
    c = np.ndarray.tolist(b)
    d = c[-1]
    layerName = d[:-5]

    #Execute gdalwarp
    cmd = f"gdalwarp -overwrite -s_srs EPSG:{str(EPSG)} -t_srs EPSG:{str(EPSG)} -of GTiff -cutline {str(maskFile)} -cl {str(layerName)} -crop_to_cutline {str(srcFile)} {str(dstFile)}"
    os.system(cmd)

    return


def pvalue_test(z,layersList):

    #Decide whether to conduct an upward or downward test depending on the sign of z
    
    if z <= float(0): 
        
        #H0: no monotonic trend ; versus H1: downward monotonic trend
    
        p_value = scipy.stats.norm.cdf(z)
        #Find alpha (significance level) such that H0 is rejected over H1, i.e. alpha | p_value < alpha (alpha such that z_value is significant)
        c = []
        for alpha in np.arange(0.01,0.98,1/100):
            if p_value < alpha:
                c.append(alpha)
            else:
                pass
        if len(c) != 0:
            first = c[0]
            confidence = 1 - first
        else:
            confidence = 0

    else:

        #H0: no monotonic trend ; versus H1: upward monotonic trend
        
        p_value = 1 - scipy.stats.norm.cdf(z)
        #Find alpha (significance level) such that H0 is rejected over H1, i.e. alpha | (1-p_value) - alpha < 0 (alpha such that z_value is significant)
        c = []
        for alpha in np.arange(0.01,0.98,1/100):
            if p_value < alpha:
                c.append(alpha)
            else:
                pass
        if len(c) != 0:
            first = c[0]
            confidence = 1 - first
        else:
            confidence = 0

    return



