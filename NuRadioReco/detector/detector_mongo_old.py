from pymongo import MongoClient
import six
import os
import sys
import pymongo
import datetime
# pprint library is used to make the output look more pretty
from pprint import pprint
import logging
import urllib.parse
import json
from bson import json_util #bson dicts are used by pymongo
import numpy as np
import pandas as pd
from NuRadioReco.utilities import units
import NuRadioReco.utilities.metaclasses
from NuRadioReco.detector.webinterface import config
logging.basicConfig()
logger = logging.getLogger("database")
logger.setLevel(logging.DEBUG)



@six.add_metaclass(NuRadioReco.utilities.metaclasses.Singleton)
class Detector(object):

    def __init__(self, database_connection = "env_pw_user", database_name=None):

        if database_connection == "local":
            MONGODB_URL = "localhost"
            self.__mongo_client = MongoClient(MONGODB_URL)
            self.db = self.__mongo_client.RNOG_live
        elif database_connection == "env_url":
            # connect to MongoDB, change the << MONGODB_URL >> to reflect your own connection string
            MONGODB_URL = os.environ.get('MONGODB_URL')
            if MONGODB_URL is None:
                logger.warning('MONGODB_URL not set, defaulting to "localhost"')
                MONGODB_URL = 'localhost'
            self.__mongo_client = MongoClient(MONGODB_URL)
            self.db = self.__mongo_client.RNOG_live
        elif database_connection == "env_pw_user":
            # use db connection from environment, pw and user need to be percent escaped
            mongo_password = urllib.parse.quote_plus(os.environ.get('mongo_password'))
            mongo_user = urllib.parse.quote_plus(os.environ.get('mongo_user'))
            mongo_server = os.environ.get('mongo_server')
            if mongo_server is None:
                logger.warning('variable "mongo_server" not set')
            if None in [mongo_user, mongo_server]:
                logger.warning('"mongo_user" or "mongo_password" not set')
            # start client
            self.__mongo_client = MongoClient("mongodb://{}:{}@{}".format(mongo_user, mongo_password, mongo_server), tls=True)
            self.db = self.__mongo_client.RNOG_live
        elif database_connection == "test":
            self.__mongo_client = MongoClient("mongodb+srv://RNOG_test:TTERqY1YWBYB0KcL@cluster0-fc0my.mongodb.net/test?retryWrites=true&w=majority")
            self.db = self.__mongo_client.RNOG_test
        elif database_connection == "RNOG_public":
            self.__mongo_client = MongoClient("mongodb://read:EseNbGVaCV4pBBrt@radio.zeuthen.desy.de:27017/admin?authSource=admin&readPreference=primary&appname=MongoDB%20Compass&directConnection=true&ssl=true")
            #self.__mongo_client = MongoClient("mongodb+srv://RNOG_read:7-fqTRedi$_f43Q@cluster0-fc0my.mongodb.net/test?retryWrites=true&w=majority")
            self.db = self.__mongo_client.RNOG_live
        elif isinstance(database_connection, str):
            logger.info(f'trying to connect to {database_connection} ...')
            self.__mongo_client = MongoClient(database_connection)
            logger.info(f'looking for {database_name} ...')
            self.db = self.__mongo_client.get_database(database_name)
        else:
            logger.error('specify a defined database connection ["local", "env_url", "env_pw_user", "test"]')

        logger.info("database connection to {} established".format(self.db.name))

        self.__current_time = None

        self.__modification_timestamps = self._query_modification_timestamps()
        self.__buffered_period = None

        # just for testing
        # logger.info("setting detector time to current time")
        # self.update(datetime.datetime.now())


    # TODO copy to new
    def update(self, timestamp):
        logger.info("updating detector time to {}".format(timestamp))
        self.__current_time = timestamp
        self._update_buffer()
    # TODO copy to new
    def export_detector(self, filename="detector.json"):
        """ export the detector to file """

        if os.path.exists(filename):
            logger.error("Output file already exists.")
        else:
            self.__db["detector_time"] = self.__current_time
            with open(filename, 'w') as fp:
                fp.write(json_util.dumps(self.__db, indent=4, sort_keys=True))
                #Note: some output/timezone options can be set in bson.json_util.DEFAULT_JSON_OPTIONS
            logger.info("Output written to {}.".format(filename))
    # TODO copy to new            
    def import_detector(self, filename):
        """ import the detector from file """
        if os.path.isfile(filename):
            logger.info("Importing detector from file {}".format(filename))

            self.__det = json.load(open(filename))
            self._current_time = self.__det["detector_time"]
        else:
            logger.error("Cannot import detector. File {} does not exist.".format(filename))

    def add_station(self,
                    station_id,
                    station_name,
                    position,  # in GPS UTM coordinates
                    commission_time,
                    decommission_time=datetime.datetime(2080, 1, 1)):
        if(self.db.station.count_documents({'id': station_id}) > 0):
            logger.error(f"station with id {station_id} already exists. Doing nothing.")
        else:
            self.db.station.insert_one({'id': station_id,
                                        'name': station_name,
                                        'position': list(position),
                                        'commission_time': commission_time,
                                        'decommission_time': decommission_time
                                        })

    def add_channel_to_station(self,
                               station_id,
                               channel_id,
                               signal_chain,
                               ant_name,
                               ant_ori_theta,
                               ant_ori_phi,
                               ant_rot_theta,
                               ant_rot_phi,
                               ant_position,
                               channel_type,
                               commission_time,
                               decommission_time=datetime.datetime(2080, 1, 1)):
        unique_station_id = self.db.station.find_one({'id': station_id})['_id']
        if(self.db.station.count_documents({'id': station_id, "channels.id": channel_id}) > 0):
            logger.error(f"channel with id {channel_id} already exists. Doing nothing.")
            return 1

        self.db.station.update_one({'_id': unique_station_id},
                               {"$push": {'channels': {
                                   'id': channel_id,
                                   'ant_name': ant_name,
                                   'ant_position': list(ant_position),
                                   'ant_ori_theta': ant_ori_theta,
                                   'ant_ori_phi': ant_ori_phi,
                                   'ant_rot_theta': ant_rot_theta,
                                   'ant_rot_phi': ant_rot_phi,
                                   'type': channel_type,
                                   'commission_time': commission_time,
                                   'decommission_time': decommission_time,
                                   'signal_ch': signal_chain
                                   }}
                               })

    # TODO copy to new
    def _update_buffer(self, force=False):
        """
        updates the buffer if need be

        Parameters
        ---------
        force: bool
            update even if the period has already been buffered
        """

        # digitize the current time of the detector to check if this period is already buffered or not
        current_period = np.digitize(self.__current_time.timestamp(), self.__modification_timestamps)
        if self.__buffered_period == current_period:
            logger.info("period already buffered")
        else:
            logger.info("buffering new period")
            self.__buffered_period = current_period
            #TODO do buffering, needs to be implemented, take whole db for now
            self.__db = {}
            self._buffer_stations()
            self._buffer_hardware_components()

    # TODO copy to new
    def _buffer_stations(self):
        """ write stations and channels for the current time to the buffer """

        # grouping dictionary is needed to undo the unwind
        grouping_dict = {"_id": "$_id", "channels": {"$push": "$channels"}}
        # add other keys that belong to a station
        for key in list(self.db.station.find_one().keys()):
            if key in grouping_dict:
                continue
            else:
                grouping_dict[key] = {"$first": "${}".format(key)}

        time = self.__current_time
        time_filter = [{"$match": {
                            'commission_time': {"$lte" : time},
                            'decommission_time': {"$gte" : time}}},
                       {"$unwind": '$channels'},
                       {"$match": {
                            'channels.commission_time': {"$lte" : time},
                            'channels.decommission_time': {"$gte" : time}}},
                       { "$group": grouping_dict}]
        stations_for_buffer = list(self.db.station.aggregate(time_filter))

        # convert nested lists of dicts to nested dicts of dicts
        self.__db["stations"] = dictionarize_nested_lists(stations_for_buffer, parent_key="id", nested_field="channels", nested_key="id")

    # TODO copy to new
    def _find_hardware_components(self):
        """
        returns hardware component names grouped by hardware type at the current detector time

        Return
        -------------
        dict with hardware component names grouped by hardware type
        """
        time = self.__current_time
        # filter for current time, and return only hardware component types and names
        component_filter = [{"$match": {
                              'commission_time': {"$lte" : time},
                              'decommission_time': {"$gte" : time}}},
                         {"$unwind": '$channels'},
                         {"$match": {
                              'channels.commission_time': {"$lte" : time},
                              'channels.decommission_time': {"$gte" : time}}},
                         {"$unwind": '$channels.signal_ch'},
                         {"$project": {"_id": False, "channels.signal_ch.uname": True,  "channels.signal_ch.type": True}}]

        # convert result to the dict of hardware types / names
        components = {}
        for item in list(self.db.station.aggregate(component_filter)):
            if not 'signal_ch' in item['channels']:
                ## continue silently
                #logger.debug("'signal_ch' not in db entry, continuing")
                continue
            ch_type = item['channels']['signal_ch']['type']
            ch_uname = item['channels']['signal_ch']['uname']
            # only add each component once
            if ch_type not in components:
                components[ch_type] = set([])
            components[ch_type].add(ch_uname)
        # convert sets to lists
        for key in components.keys():
            components[key] = list(components[key])
            logger.info(f"found {len(components[key])} hardware components in {key}: {components[key]}")
        return components

    # TODO copy to new, probably needs some modification
    def _buffer_hardware_components(self, S_parameters = ["S21"]):
        """
        buffer all the components which appear in the current detector

        Parameters
        ----------
        S_parameters: list
            list of S-parameters to buffer
        """
        component_dict = self._find_hardware_components()

        nested_key_dict = {"SURFACE": "surface_channel_id", "DRAB": "drab_channel_id"}
        for hardware_type in component_dict:
            # grouping dictionary is needed to undo the unwind
            grouping_dict = {"_id": "$_id", "measurements": {"$push": "$measurements"}}

            if self.db[hardware_type].find_one() is None:
                print(f"DB for {hardware_type} is empty. Skipping...")
                continue
            # add other keys that belong to a station
            for key in list(self.db[hardware_type].find_one().keys()):
                if key in grouping_dict:
                    continue
                else:
                    grouping_dict[key] = {"$first": "${}".format(key)}

            #TODO select more accurately. is there a "primary" mesurement field? is S_parameter_XXX matching possible to reduce data?
            matching_components = list(self.db[hardware_type].aggregate([{"$match": {"name": {"$in": component_dict[hardware_type]}}},
                                                                         {"$unwind": "$measurements"},
                                                                         {"$match": {"measurements.primary_measurement": True,
                                                                                     "measurements.S_parameter": {"$in": S_parameters}}},
                                                                         {"$group": grouping_dict}]))
            #TODO wind #only S21?
            #list to dict conversion using "name" as keys
            print(f"Component entries found in {hardware_type}: {len(matching_components)}")
            if len(matching_components)==0:
                continue
            try:
                self.__db[hardware_type] = dictionarize_nested_lists_as_tuples(matching_components,
                        parent_key="name",
                        nested_field="measurements",
                        nested_keys=("channel_id","S_parameter"))
            except:
                continue

            #print("there")
            #self.__db[hardware_type] = dictionarize_nested_lists(matching_components, parent_key="name", nested_field=None, nested_key=None)

        print("done...")

    # TODO copy to new
    # TODO this is probably not used, unless we want to update on a per-station level
    def _query_modification_timestamps_per_station(self):
        """
        collects all the timestamps from the database for which some modifications happened
        ((de)commissioning of stations and channels).

        Return
        -------------
        dict with modification timestamps per station.id
        """
        # get distinct set of stations:
        station_ids = self.db.station.distinct("id")
        modification_timestamp_dict = {}

        for station_id in station_ids:
            # get set of (de)commission times for stations
            station_times_comm = self.db.station.distinct("commission_time", {"id": station_id})
            station_times_decomm = self.db.station.distinct("decommission_time", {"id": station_id})

            # get set of (de)commission times for channels
            channel_times_comm = self.db.station.distinct("channels.commission_time", {"id": station_id})
            channel_times_decomm = self.db.station.distinct("channels.decommission_time", {"id": station_id})

            mod_set = np.unique([*station_times_comm,
                                 *station_times_decomm,
                                 *channel_times_comm,
                                 *channel_times_decomm])
            mod_set.sort()
            # store timestamps, which can be used with np.digitize
            modification_timestamp_dict[station_id]= [mod_t.timestamp() for mod_t in mod_set]
        return modification_timestamp_dict


    # TODO copy to new
    def _query_modification_timestamps(self):
        """
        collects all the timestamps from the database for which some modifications happened
        ((de)commissioning of stations and channels).

        Return
        -------------
        list of modification timestamps
        """
        # get set of (de)commission times for stations
        station_times_comm = self.db.station.distinct("commission_time")
        station_times_decomm = self.db.station.distinct("decommission_time")

        # get set of (de)commission times for channels
        channel_times_comm = self.db.station.distinct("channels.commission_time")
        channel_times_decomm = self.db.station.distinct("channels.decommission_time")
        mod_set = np.unique([*station_times_comm,
                             *station_times_decomm,
                             *channel_times_comm,
                             *channel_times_decomm])
        mod_set.sort()
        # store timestamps, which can be used with np.digitize
        modification_timestamps = [mod_t.timestamp() for mod_t in mod_set]
        return modification_timestamps

# TODO copy to new
def dictionarize_nested_lists(nested_lists, parent_key="id", nested_field="channels", nested_key="id"):
    """ mongodb aggregate returns lists of dicts, which can be converted to dicts of dicts """
    res = {}
    for parent in nested_lists:
        res[parent[parent_key]] = parent
        if nested_field in parent and (nested_field is not None):
            daughter_list = parent[nested_field]
            daughter_dict = {}
            for daughter in daughter_list:
                if nested_key in daughter:
                    daughter_dict[daughter[nested_key]] = daughter
                #else:
                #    logger.warning(f"trying to access unavailable nested key {nested_key} in field {nested_field}. Nothing to be done.")
            # replace list with dict
            res[parent[parent_key]][nested_field] = daughter_dict
    return res

# TODO copy to new
def dictionarize_nested_lists_as_tuples(nested_lists, parent_key="name", nested_field="measurements", nested_keys=("channel_id","S_parameter")):
    """ mongodb aggregate returns lists of dicts, which can be converted to dicts of dicts """
    res = {}
    for parent in nested_lists:
        res[parent[parent_key]] = parent
        if nested_field in parent and (nested_field is not None):
            daughter_list = parent[nested_field]
            daughter_dict = {}
            for daughter in daughter_list:
                # measurements do not have a unique column which can be used as key for the dictionnary, so use a tuple instead for indexing
                dict_key = []
                for nested_key in nested_keys:
                    if nested_key in daughter:
                        dict_key.append(daughter[nested_key])
                    else:
                        dict_key.append(None)
                daughter_dict[tuple(dict_key)] = daughter
                #else:
                #    logger.warning(f"trying to access unavailable nested key {nested_key} in field {nested_field}. Nothing to be done.")
            # replace list with dict
            res[parent[parent_key]][nested_field] = daughter_dict
    return res

# TODO probably not needed in new detector_mongo
def get_measurement_from_buffer(hardware_db, S_parameter="S21", channel_id=None):
    if channel_id is None:
        measurements = list(filter(lambda document: document['S_parameter'] == S_parameter, hardware_db["measurements"]))
    else:
        measurements = list(filter(lambda document: (document['S_parameter'] == S_parameter) & (document["channel_id"] == channel_id), hardware_db["measurements"]))
    if len(measurements)>1:
        print("WARNING: more than one match for requested measurement found")
    return measurements

det = Detector(config.DATABASE_TARGET)

if __name__ == "__main__":
     test = sys.argv[1]
     det = Detector(test)
