from wikibrain import wikimedia_link_issue_reporter
from wikibrain import wikipedia_knowledge
import wikimedia_connection.wikimedia_connection as wikimedia_connection
import config
import obtain_from_overpass
import json
import sqlite3
import generate_webpage_with_error_output
import os
import osm_bot_abstraction_layer.osm_bot_abstraction_layer as osm_bot_abstraction_layer
import time
import osm_editor_bot_for_approved_tasks

def main():
    osm_editor_bot_for_approved_tasks.main()
    check_for_malformed_definitions_of_entries()
    update_validator_database_and_reports()

def update_validator_database_and_reports():
    connection = sqlite3.connect(config.database_filepath())
    cursor = connection.cursor()
    create_table_if_needed(cursor)
    connection.commit()

    for entry in config.get_entries_to_process():
        if "hidden" in entry:
            if entry["hidden"] == True:
                continue
        generate_webpage_with_error_output.generate_website_file_for_given_area(cursor, entry)
    generate_webpage_with_error_output.write_index_and_merged_entries(cursor)
    commit_and_publish_changes_in_report_directory()

    wikimedia_connection.set_cache_location(config.get_wikimedia_connection_cache_location())

    entries_with_age = []
    for entry in config.get_entries_to_process():
        internal_region_name = entry['internal_region_name']
        timestamp = obtain_from_overpass.get_data_timestamp(cursor, internal_region_name)
        entries_with_age.append({"data": entry, "data_timestamp": timestamp})
    current_timestamp = int(time.time())
    entries_with_age = sorted(entries_with_age, key=lambda entry: -(current_timestamp - entry["data_timestamp"]) * entry["data"].get("priority_multiplier", 1))
    
    total_entry_count = len(config.get_entries_to_process())
    processed_entries = 0
    print()
    print()
    print()
    for selected_processing_entry in entries_with_age[::-1]:
        entry = selected_processing_entry['data']
        score = (current_timestamp - selected_processing_entry["data_timestamp"]) * entry.get("priority_multiplier", 1)
        k = str(int((score+500)/1000))
        print(entry['internal_region_name'], entry.get("priority_multiplier", 1), k+"k")

    for selected_processing_entry in entries_with_age:
        print()
        print()
        print(processed_entries, "/", total_entry_count)
        processed_entries += 1
        entry = selected_processing_entry['data']
        internal_region_name = entry['internal_region_name']
        print(internal_region_name)
        if "hidden" in entry:
            if entry["hidden"] == True:
                continue
        process_given_area(cursor, entry)
        connection.commit()
        generate_webpage_with_error_output.write_index_and_merged_entries(cursor) # update after each run
    connection.close()
    commit_and_publish_changes_in_report_directory()

def check_for_malformed_definitions_of_entries():
    for entry in config.get_entries_to_process():
        if "/" in entry['internal_region_name']:
            raise Exception("/ in " + entry['internal_region_name'])
        if "/" in entry['website_main_title_part']:
            raise Exception("/ in " + entry['website_main_title_part'])

def existing_tables(cursor):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    table_listing = cursor.fetchall()
    returned = []
    for entry in table_listing:
        returned.append(entry[0])
    return returned

def create_table_if_needed(cursor):
    if "osm_data" in existing_tables(cursor):
        print("osm_data table exists already, delete file with database to recreate")
    else:
        # validator_complaint needs to hold
        # - not checked
        # - checked, no problem found
        # - error data
        #
        # right now for "checked, no error" I plan to use empty string but I am not too happy
        cursor.execute('''CREATE TABLE osm_data
                    (type text, id number, lat float, lon float, tags text, area_identifier text, download_timestamp integer, validator_complaint text, error_id text)''')

        # magnificent speedup
        cursor.execute("""CREATE INDEX idx_osm_data_area_identifier ON osm_data (area_identifier);""")
        cursor.execute("""CREATE INDEX idx_osm_data_id_type ON osm_data (id, type);""")
    if "osm_data_update_log" in existing_tables(cursor):
        print("osm_data_update_log table exists already, delete file with database to recreate")
    else:
        # register when data was downloaded so update can be done without downloading
        # and processing the entire dataset
        #
        # instead just entries that were changed since then
        # - and carry *(wikipedia|wikidata)* tags
        # - that previously had problem reported about them
        # should be downloaded
        cursor.execute('''CREATE TABLE osm_data_update_log
                    (area_identifier text, filename text, download_type text, download_timestamp integer)''')

def process_given_area(cursor, entry):
    ignored_problems = entry.get('ignored_problems', [])
    update_outdated_elements(cursor, entry, ignored_problems)
    update_validator_reports_for_given_area(cursor, entry['internal_region_name'], entry.get('language_code', None), ignored_problems)
    generate_webpage_with_error_output.generate_website_file_for_given_area(cursor, entry)

def update_outdated_elements(cursor, entry, ignored_problems):
    identifier_of_region_for_overpass_query=entry['identifier']
    timestamp_when_file_was_downloaded = obtain_from_overpass.download_entry(cursor, entry['internal_region_name'], identifier_of_region_for_overpass_query)

    # properly update by fetching new info about entries which also must be updated and could be missed
    outdated_objects = outdated_entries_in_area_that_must_be_updated(cursor, entry['internal_region_name'], timestamp_when_file_was_downloaded)
    for outdated in outdated_objects:
        rowid, object_type, object_id, lat, lon, tags, area_identifier, download_timestamp, validator_complaint, error_id = outdated
        validator_complaint = json.loads(validator_complaint)
        if validator_complaint['error_id'] in ignored_problems:
            continue
        else:
            print(validator_complaint['error_id'], "IS NOT AMONG", ignored_problems)
        data = osm_bot_abstraction_layer.get_data(object_id, object_type)
        timestamp = int(time.time())
        #print(json.dumps(returned, default=str, indent=3))
        new_tags = "was deleted"
        cursor.execute("""
        DELETE FROM osm_data
        WHERE
        type = :type AND id = :id AND area_identifier = :identifier
        """, {"type": object_type, "id": object_id, "identifier": entry['internal_region_name']})
        if data != None: # None means that it was deleted
            new_tags =  json.dumps(data["tag"], indent=3) # pretty format also in database for easier debugging
            new_lat = lat
            new_lon = lon
            if object_type == "node":
                new_lat = data["lat"]
                new_lon = data["lon"]
                # what about ways and relations?
            #print(data)
            cursor.execute("INSERT INTO osm_data VALUES (:type, :id, :lat, :lon, :tags, :area_identifier, :download_timestamp, :validator_complaint, :error_id)", {'type': object_type, 'id': object_id, 'lat': new_lat, 'lon': new_lon, "tags": new_tags, "area_identifier": entry['internal_region_name'], "download_timestamp": timestamp, "validator_complaint": None, 'error_id': None})
        print(object_type, object_id, "is outdated, not in the report so its entry needs to be updated for", validator_complaint['error_id'], "in", entry['internal_region_name'])

def outdated_entries_in_area_that_must_be_updated(cursor, internal_region_name, timestamp_when_file_was_downloaded):
    # - entries currently are carrying reports and with outdated timestamps
    # (as wikipedia tag could be simply removed!)
    #
    # - entries without current wikidata/wikipedia tags may be outdated AND without active reports are safe
    #   - will not generate valid report
    #   - will not be false positives

    cursor.execute("""SELECT rowid, type, id, lat, lon, tags, area_identifier, download_timestamp, validator_complaint, error_id
    FROM osm_data
    WHERE
    area_identifier = :identifier
    AND
    download_timestamp < :timestamp_when_file_was_downloaded
    AND
    validator_complaint IS NOT NULL
    AND
    validator_complaint <> ""
    """, {"identifier": internal_region_name, "timestamp_when_file_was_downloaded": timestamp_when_file_was_downloaded})
    return cursor.fetchall()

def update_validator_reports_for_given_area(cursor, internal_region_name, language_code, ignored_problems):
    detect_problems_using_cache_for_wikimedia_data(cursor, internal_region_name, language_code)
    print("SKIPPING CACHE REFRESH OF WIKIDATA DATA") # TODO reestablish it in a proper way
    #print("NOW CHECKING WHAT WAS REPORTED WITHOUT USING CACHE!")
    #verify_that_problem_exist_without_using_cache_for_wikimedia_data(cursor, internal_region_name, language_code, ignored_problems)

def detect_problems_using_cache_for_wikimedia_data(cursor, internal_region_name, language_code):
    issue_detector = get_wikimedia_link_issue_reporter_object(language_code)
    # will recheck reported errors
    # will not recheck entries that previously were free of errors
    cursor.execute('SELECT rowid, type, id, lat, lon, tags, area_identifier, download_timestamp, validator_complaint, error_id FROM osm_data WHERE area_identifier = :identifier AND validator_complaint IS NULL', {"identifier": internal_region_name})
    entries = cursor.fetchall()
    update_problem_for_all_this_entries(issue_detector, cursor, entries, [])

def verify_that_problem_exist_without_using_cache_for_wikimedia_data(cursor, internal_region_name, language_code, ignored_problems):
    issue_detector_refreshing_cache = get_wikimedia_link_issue_reporter_object(language_code, forced_refresh=True)
    # recheck reported with request to fetch cache
    # done separately to avoid refetching over and over again where everything is fine
    # (say, tags on a road/river)
    cursor.execute('SELECT rowid, type, id, lat, lon, tags, area_identifier, download_timestamp, validator_complaint, error_id FROM osm_data WHERE area_identifier = :identifier AND validator_complaint IS NOT NULL AND validator_complaint <> ""', {"identifier": internal_region_name})
    entries = cursor.fetchall()
    update_problem_for_all_this_entries(issue_detector_refreshing_cache, cursor, entries, ignored_problems)

def update_problem_for_all_this_entries(issue_detector, cursor, entries, ignored_problems):
    for entry in entries:
        rowid, object_type, object_id, lat, lon, tags, area_identifier, download_timestamp, validator_complaint, error_id = entry
        tags = json.loads(tags)
        location = (lat, lon)
        object_description = object_type + "/" + str(object_id)
        if validator_complaint != None:
            if len(ignored_problems) > 0:
                validator_complaint = json.loads(validator_complaint)
                if validator_complaint['error_id'] in ignored_problems:
                    continue
        update_problem_for_entry(issue_detector, cursor, tags, location, object_type, object_id, object_description, rowid)

def update_problem_for_entry(issue_detector, cursor, tags, location, object_type, object_id, object_description, rowid):
        object_description = object_type + "/" + str(object_id)
        reported = issue_detector.get_the_most_important_problem_generic(tags, location, object_type, object_description)
        if reported != None:
            link = "https://openstreetmap.org/" + object_type + "/" + str(object_id)
            data = reported.data()
            data['osm_object_url'] = link # TODO eliminate need for this
            data['tags'] = tags # TODO eliminate need for this
            error_id = data['error_id']
            data = json.dumps(data)
            cursor.execute("""UPDATE osm_data 
            SET validator_complaint = :validator_complaint,
                error_id = :error_id
            WHERE rowid = :rowid""",
            {"validator_complaint": data, "error_id": error_id, "rowid": rowid})
        else:
            cursor.execute("""UPDATE osm_data
            SET validator_complaint = :validator_complaint,
                error_id = :error_id
            WHERE rowid = :rowid""",
            {"validator_complaint": "", "error_id": "", "rowid": rowid})

def get_wikimedia_link_issue_reporter_object(language_code, forced_refresh=False):
    return wikimedia_link_issue_reporter.WikimediaLinkIssueDetector(
        forced_refresh=forced_refresh,
        expected_language_code=language_code, # may be None
        languages_ordered_by_preference=[language_code],
        additional_debug=False,
        allow_requesting_edits_outside_osm=False,
        allow_false_positives=False
        )

def commit_and_publish_changes_in_report_directory():
    current_working_directory = os.getcwd()
    os.chdir(config.get_report_directory())
    os.system('git add index.html')
    os.system('git commit -m "automatic update of index.html"')
    os.system('git add --all')
    os.system('git commit -m "automatic update of report files"')
    os.system('git push')
    os.chdir(current_working_directory)

main()
