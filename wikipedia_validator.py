# coding=utf-8

import urllib.request, urllib.error, urllib.parse
import argparse
import yaml

import wikipedia_connection
from osm_iterator import Data

def get_problem_for_given_element(element, forced_refresh):
    if args.flush_cache:
        forced_refresh = True
    link = element.get_tag_value("wikipedia")
    if link == None:
        return None

    #TODO - is it OK?
    #if link.find("#") != -1:
    #    return "link to section (\"only provide links to articles which are 'about the feature'\" - http://wiki.openstreetmap.org/wiki/Key:wikipedia):"

    language_code = wikipedia_connection.get_language_code_from_link(link)
    article_name = wikipedia_connection.get_article_name_from_link(link)
    wikidata_id = wikipedia_connection.get_wikidata_object_id_from_article(language_code, article_name, forced_refresh)

    if language_code is None or language_code.__len__() > 3:
        return ErrorReport(error_id = "malformed wikipedia tag", error_message = "malformed wikipedia tag (" + link + ")")

    page = wikipedia_connection.get_wikipedia_page(language_code, article_name, forced_refresh)

    if page == None:
        return ErrorReport(error_id = "wikipedia tag links to 404", error_message = "missing article at wiki:")

    wikipedia_link_issues = get_problem_based_on_wikidata(element, page, language_code, article_name, wikidata_id)
    if wikipedia_link_issues != None:
        return wikipedia_link_issues

    reason = why_object_is_allowed_to_have_foreign_language_label(element, wikidata_id)
    if reason != None:
        print(describe_osm_object(element) + " is allowed to have foreign wikipedia link, because " + reason)
    else:
        if args.expected_language_code is not None and args.expected_language_code != language_code:
            correct_article = get_interwiki(language_code, article_name, args.expected_language_code, forced_refresh)
            if correct_article != None:
                error_message = "wikipedia page in unwanted language - " + args.expected_language_code + " was expected:"
                return ErrorReport(error_id = "wikipedia tag relinking necessary", error_message = error_message)
            if correct_article == None and args.only_osm_edits == False and args.allow_false_positives:
                error_message = "wikipedia page in unwanted language - " + args.expected_language_code + " was expected, no page in that language was found:"
                return ErrorReport(error_id = "wikipedia tag relinking desirable, article missing", error_message = error_message)
    if args.only_osm_edits == False:
        return get_geotagging_problem(page, element, wikidata_id)

    return None

def get_problem_based_on_wikidata(element, page, language_code, article_name, wikidata_id):
    if not element_can_be_reduced_to_position_at_single_location(element):
        return None
    if is_wikipedia_page_geotagged(page) or wikipedia_connection.get_location_from_wikidata(wikidata_id) != (None, None):
        return None
    if wikidata_id == -1:
        return ErrorReport(error_id = "wikidata entry missing", error_message = describe_osm_object(element) + " has no matching wikidata entry")

    base_type_id = get_wikidata_type_id_from_article(language_code, article_name)
    if base_type_id == None:
        if args.only_osm_edits:
            return None
        error_message = "instance data not present in wikidata for " + wikidata_url(language_code, article_name) + ". unable to verify type of object:"
        return ErrorReport(error_id = "wikidata data missing - instance", error_message = error_message)
    all_types = recursive_all_subclass_of(base_type_id)
    for type_id in all_types:
        if type_id == 'Q4167410':
            error_message = wikipedia_url(language_code, article_name) + " is a disambig page - not a proper wikipedia link"
            return ErrorReport(error_id = "link to disambig", error_message = error_message)
        if type_id == 'Q5':
            error_message = "article linked in wikipedia tag is about human, so it is very unlikely to be correct (subject:wikipedia=* tag would be probably better - in case of change remember to remove wikidata tag if it is present)"
            return ErrorReport(error_id = "link to human", error_message = error_message)
        if type_id == 'Q43229':
            error_message = "article linked in wikipedia tag is about organization, so it is very unlikely to be correct (brand:wikipedia=* or operator:wikipedia=* tag would be probably better - in case of change remember to remove wikidata tag if it is present)"
            return ErrorReport(error_id = "link to organization", error_message = "")
    for type_id in all_types:
        if type_id == 'Q486972':
            #"human settlement"
            return None
        if type_id == 'Q811979':
            #"designed structure"
            return None
        if type_id == 'Q46831':
            # mountain range - "geographic area containing numerous geologically related mountains"
            return None
        if type_id == 'Q11776944':
            # Megaregion
            return None
        if type_id == 'Q31855':
            #instytut badawczy
            return None
        if type_id == 'Q34442':
            #road
            return None
        if type_id == 'Q2143825':
            #walking path 'path for hiking in a natural environment'
            return None
        if type_id == 'Q11634':
            #'art of sculpture'
            return None
        if type_id == 'Q56061':
            #'administrative territorial entity' - 'territorial entity for administration purposes, with or without its own local government'
            return None
        if type_id == 'Q473972':
            #'protected area'
            return None
        if type_id == 'Q4022':
            #river
            return None
        if type_id == 'Q22698':
            #park
            return None
        if type_id == 'Q11446':
            #ship
            return None
        if type_id == 'Q57607':
            #christmas market
            return None



    print("------------")
    print(describe_osm_object(element))
    print("unexpected type " + base_type_id)
    describe_unexpected_wikidata_type(base_type_id)

def wikidata_entries_for_abstract_or_very_broad_concepts():
    return ['Q1801244', 'Q28732711', 'Q223557', 'Q488383', 'Q16686448',
    'Q151885', 'Q35120', 'Q37260', 'Q246672', 'Q5127848', 'Q16889133',
    'Q386724', 'Q17008256', 'Q11348', 'Q11028', 'Q1260632', 'Q1209283']

def recursive_all_subclass_of(wikidata_id):
    processed = []
    to_process = [wikidata_id]
    while to_process != []:
        process_id = to_process.pop()
        processed.append(process_id)
        to_process += get_useful_direct_parents(process_id, processed + to_process)
    return processed

def get_useful_direct_parents(wikidata_id, forbidden):
    more_general_list = wikipedia_connection.get_property_from_wikidata(wikidata_id, 'P279') #subclass of
    if more_general_list == None:
        return []
    returned = []
    for more_general in more_general_list:
        more_general_id = more_general['mainsnak']['datavalue']['value']['id']
        if more_general_id not in forbidden:
            if more_general_id not in wikidata_entries_for_abstract_or_very_broad_concepts():
                returned.append(more_general_id)
    return returned

def describe_unexpected_wikidata_type(type_id):
    # print entire inheritance set
    for parent_category in recursive_all_subclass_of(type_id):
        print("if type_id == '" + parent_category + "':")
        show_wikidata_description(parent_category)

def show_wikidata_description(wikidata_id):
    en_docs = get_wikidata_description(wikidata_id, 'en')
    local_docs = get_wikidata_description(wikidata_id, args.expected_language_code)
    print(en_docs)
    if(en_docs == (None, None)):
        print(local_docs)
        if(local_docs == (None, None)):
            print("Unexpected type " + wikidata_id + " undocumented format")

def get_wikidata_description(wikidata_id, language):
    docs = wikipedia_connection.get_data_from_wikidata_by_id(wikidata_id)
    returned = ""
    label = None
    try:
        label = docs['entities'][wikidata_id]['labels'][language]['value']
    except KeyError:
        label = None

    explanation = None
    try:
        explanation = docs['entities'][wikidata_id]['descriptions'][language]['value']
    except KeyError:
        explanation = None

    return dict(label = label, explanation = explanation, language = language)

def get_wikidata_type_id_from_article(language_code, article_name):
    try:
        forced_refresh = False
        wikidata_entry = wikipedia_connection.get_data_from_wikidata(language_code, article_name, forced_refresh)
        wikidata_entry = wikidata_entry['entities']
        object_id = list(wikidata_entry)[0]
        return wikidata_entry[object_id]['claims']['P31'][0]['mainsnak']['datavalue']['value']['id']
    except KeyError:
        return None

# unknown data, known to be completely inside -> not allowed, returns None
# known to be outside or on border -> allowed, returns reason
def why_object_is_allowed_to_have_foreign_language_label(element, wikidata_id):
    if args.expected_language_code == None:
        return "no expected language is defined"

    if args.expected_language_code == "pl":
        target = 'Q36' #TODO, make it more general
    elif args.expected_language_code == "de":
        target = 'Q183'
    else:
        assert(False)

    countries = wikipedia_connection.get_property_from_wikidata(wikidata_id, 'P17')
    if countries == None:
        # TODO locate based on coordinates...
        return None
    for country in countries:
        country_id = country['mainsnak']['datavalue']['value']['id']
        if country_id != target:
            # we need to check whatever locations till belongs to a given country
            # it is necessary to avoid gems like
            # "Płock is allowed to have foreign wikipedia link, because it is at least partially in Nazi Germany"
            # P582 indicates the time an item ceases to exist or a statement stops being valid
            try:
                country['qualifiers']['P582']
            except KeyError:
                country_name = get_wikidata_description(country_id, 'en')['label']
                #P582 is missing, therefore it is no longer valid
                if country_id == 'Q7318':
                    print(describe_osm_object(element) + " is tagged on wikidata as location in no longer existing " + country_name)
                    return None
                return "it is at least partially in " + country_name
    return None

def element_can_be_reduced_to_position_at_single_location(element):
    if element.get_element().tag == "relation":
        relation_type = element.get_tag_value("type")
        if relation_type == "person" or relation_type == "route":
            return False
    if element.get_tag_value("waterway") == "river":
        return False
    return True


def wikipedia_location_data(lat, lon, language_code):
    lat = "%.4f" % lat  # drop overprecision
    lon = "%.4f" % lon  # drop overprecision

    returned = ""

    returned += lat + "\n"
    returned += lon + "\n"
    if language_code == "it":
        returned += "{{coord|" + lat + "|" + lon + "|display=title}}\n"
    elif language_code == "pl":
        returned += "{{współrzędne|" + lat + " " + lon + "|umieść=na górze}}\n"
        returned += "\n"
        returned += lat + " " + lon + "\n"
        returned += "\n"
        returned += pl_wikipedia_coordinates_for_infobox_old_style(float(lat), float(lon))
    else:
        returned += "{{coord|" + lat + "|" + lon + "}}\n"
    return returned

def pl_wikipedia_coordinates_for_infobox_old_style(lat, lon):
    lat_sign_character = "N"
    if lat < 0:
        lat *= -1
        lat_sign_character = "S"
    lon_sign_character = "E"
    if lon < 0:
        lon *= -1
        lon_sign_character = "W"
    lat_d = int(float(lat))
    lat_m = int((float(lat) * 60) - (lat_d * 60))
    lat_s = int((float(lat) * 60 * 60) - (lat_d * 60 * 60) - (lat_m * 60))
    lat_d = str(lat_d)
    lat_m = str(lat_m)
    lat_s = str(lat_s)
    lon_d = int(float(lon))
    lon_m = int((float(lon) * 60) - (lon_d * 60))
    lon_s = int((float(lon) * 60 * 60) - (lon_d * 60 * 60) - (lon_m * 60))
    lon_d = str(lon_d)
    lon_m = str(lon_m)
    lon_s = str(lon_s)
    pl_format = "|stopni" + lat_sign_character + " = " + lat_d
    pl_format += " |minut" + lat_sign_character + " = " + lat_m
    pl_format += " |sekund" + lat_sign_character + " = " + lat_s
    pl_format += "\n"
    pl_format += "|stopni" + lon_sign_character + " = " + lon_d
    pl_format += " |minut" + lon_sign_character + " = " + lon_m
    pl_format += " |sekund" + lon_sign_character + " = " + lon_s
    pl_format += "\n"
    return pl_format


def wikidata_url(language_code, article_name):
    return "https://www.wikidata.org/wiki/" + wikipedia_connection.get_wikidata_object_id_from_article(language_code, article_name)

def wikipedia_url(language_code, article_name):
    return "https://" + language_code + ".wikipedia.org/wiki/" + urllib.parse.quote(article_name)

def get_interwiki(source_language_code, source_article_name, target_language, forced_refresh):
    try:
        wikidata_entry = wikipedia_connection.get_data_from_wikidata(source_language_code, source_article_name, forced_refresh)
        wikidata_entry = wikidata_entry['entities']
        id = list(wikidata_entry)[0]
        return wikidata_entry[id]['sitelinks'][target_language+'wiki']['title']
    except KeyError:
        return None

class ErrorReport:
    def __init__(self, error_message=None, element=None, desired_wikipedia_target=None, coords_for_wikipedia=None, debug_log=None,
        error_id=None, fixable_by_pure_osm_edit=None, false_positive_chance=None):
        self.error_id = error_id
        self.error_message = error_message
        self.debug_log = debug_log
        self.element = element
        self.false_positive_chance = false_positive_chance
        self.fixable_by_pure_osm_edit = fixable_by_pure_osm_edit
        self.desired_wikipedia_target = desired_wikipedia_target
        self.coords_for_wikipedia = coords_for_wikipedia

    def yaml_output(self, filepath):
        data = dict(
            error_id = self.error_id,
            error_message = self.error_message,
            debug_log = self.debug_log,
            false_positive_chance = self.false_positive_chance,
            fixable_by_pure_osm_edit = self.fixable_by_pure_osm_edit,
            osm_object_description = describe_osm_object(self.element),
            osm_object_url = self.element.get_link(),
            current_wikipedia_target = self.element.get_tag_value("wikipedia"),
            desired_wikipedia_target = self.desired_wikipedia_target,
            coords_for_wikipedia = self.coords_for_wikipedia,
        )
        with open(filepath, 'a') as outfile:
            yaml.dump([data], outfile, default_flow_style=False)

    def stdout_output(self):
        print()
        print(self.error_message)
        print(describe_osm_object(self.element))
        print(self.element.get_link())
        print(self.debug_log)
        print(self.coords_for_wikipedia)
        if self.desired_wikipedia_target != None:
            print("wikipedia tag should probably be relinked to " + self.desired_wikipedia_target)
        print(self.coords_for_wikipedia)

def describe_osm_object(element):
    name = element.get_tag_value("name")
    if name == None:
        name = ""
    return name + " " + element.get_link()

def output_element(element, error_report):
    error_report.element = element
    link = element.get_tag_value("wikipedia")
    language_code = wikipedia_connection.get_language_code_from_link(link)
    article_name = wikipedia_connection.get_article_name_from_link(link)
    lat, lon = get_location_of_element(element)

    debug_log = None
    if language_code is not None and article_name is not None:
        error_report.desired_wikipedia_target = find_desired_wikipedia_link(language_code, article_name)

    if (lat, lon) == (None, None):
        error_report.debug_log = "Location data missing"
    else:
        error_report.coords_for_wikipedia = wikipedia_location_data(lat, lon, language_code)

    error_report.stdout_output()
    error_report.yaml_output(yaml_report_filepath())

def yaml_report_filepath():
    return get_write_location()+"/reported.yaml"

def get_location_of_element(element):
    lat = None
    lon = None
    if element.get_element().tag == "node":
        lat = float(element.get_element().attrib['lat'])
        lon = float(element.get_element().attrib['lon'])
        return lat, lon
    elif element.get_element().tag == "way" or element.get_element().tag == "relation":
        coord = element.get_coords()
        if coord is None:
            return None, None
        else:
            return float(coord.lat), float(coord.lon)
    assert(False)

def find_desired_wikipedia_link(language_code, article_name):
    if args.expected_language_code == None:
        return language_code + ":" + article_name
    article_name_in_intended = get_interwiki(language_code, article_name, args.expected_language_code, False)
    if article_name_in_intended == None:
        return None
    else:
        return args.expected_language_code + ":" + article_name_in_intended

def is_wikipedia_page_geotagged(page):
    # <span class="latitude">50°04'02”N</span>&#160;<span class="longitude">19°55'03”E</span>
    index = page.find("<span class=\"latitude\">")
    inline = page.find("coordinates inline plainlinks")
    if index > inline != -1:
        index = -1  #inline coordinates are not real ones
    if index == -1:
        kml_data_str = "><span id=\"coordinates\"><b>Route map</b>: <a rel=\"nofollow\" class=\"external text\""
        if page.find(kml_data_str) == -1:  #enwiki article links to area, not point (see 'Central Park')
            return False
    return True

def get_geotagging_problem(page, element, wikidata_id):
    if is_wikipedia_page_geotagged(page) or wikipedia_connection.get_location_from_wikidata(wikidata_id) != (None, None):
        return None
    if element_can_be_reduced_to_position_at_single_location(element):
        message = "missing coordinates at wiki or wikipedia tag should be replaced by something like operator:wikipedia=en:McDonald's or subject:wikipedia=*:"
        return ErrorReport(error_id = "target of linking is without coordinates", error_message = message)
    return None

def validate_wikipedia_link_on_element_and_print_problems(element):
    problem = get_problem_for_given_element(element, False)
    if (problem != None):
        output_element(element, problem)

def validate_wikipedia_link_on_element_and_print_problems_refresh_cache_for_reported(element):
    if(get_problem_for_given_element(element, False) != None):
        get_problem_for_given_element(element, True)
    validate_wikipedia_link_on_element_and_print_problems(element)


def parsed_args():
    parser = argparse.ArgumentParser(description='Validation of wikipedia tag in osm data.')
    parser.add_argument('-expected_language_code', '-l', dest='expected_language_code', type=str, help='expected language code')
    parser.add_argument('-file', '-f', dest='file', type=str, help='location of .osm file')
    parser.add_argument('-flush_cache', dest='flush_cache', help='adding this parameter will trigger flushing cache',
                        action='store_true')
    parser.add_argument('-flush_cache_for_reported_situations', dest='flush_cache_for_reported_situations',
                        help='adding this parameter will trigger flushing cache only for reported situations \
                        (redownloads wikipedia data for cases where errors are reported, \
                        so removes false positives where wikipedia is already fixed)',
                        action='store_true')
    parser.add_argument('-only_osm_edits', dest='only_osm_edits', help='adding this parameter will remove reporting of problems that may require editing wikipedia',
                        action='store_true')
    parser.add_argument('-allow_false_positives', dest='allow_false_positives', help='enables validator rules that may report false positives')
    args = parser.parse_args()
    if not (args.file):
        parser.error('Provide .osm file')
    return args

def get_write_location():
    cache_location_config_filepath = 'cache_location.config'
    cache_location_file = open(cache_location_config_filepath, 'r')
    returned = cache_location_file.read()
    cache_location_file.close()
    return returned

wikipedia_connection.set_cache_location(get_write_location())

args = parsed_args()
osm = Data(args.file)
if args.flush_cache_for_reported_situations:
    osm.iterate_over_data(validate_wikipedia_link_on_element_and_print_problems_refresh_cache_for_reported)
else:
    osm.iterate_over_data(validate_wikipedia_link_on_element_and_print_problems)
