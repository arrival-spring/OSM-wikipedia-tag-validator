import osm_bot_abstraction_layer.world_data as world_data
import yaml

def main():
    returned = ""
    # "ISO3166-1", "ISO3166-1:alpha2", "ISO3166-2" tags can be used
    for ISO3166 in []: # 'JP', 'IR', 'PL'
        returned += "\n"
        returned += "\n"
        print(world_data.list_of_area_divisions_data(ISO3166, 4, ["name", "wikidata"], '/tmp/boundary_data.osm'))

    processed = [
        {
        'code': 'US-TX',
        'parent': "USA",
        'extra_part_of_name': "Texas",
        'language_code': "en",
        'requested_by': 'skquinn via PM in https://www.openstreetmap.org/messages/924460 and Bman via PM in https://www.openstreetmap.org/messages/1054938',
        }
    ]
    for source in processed: # 'JP', 'IR', 'PL'
        returned += "\n"
        returned += "\n"
        ISO3166 = source['code']
        data = world_data.list_of_area_divisions_data(ISO3166, 6, ["name", "wikidata", "name:pl", "name:en"], '/tmp/boundary_data.osm')
        for osm_data in data:
            returned += generate_osm_data_in_region_list(source, osm_data)
            returned += "\n"
    print(returned)

def generate_osm_data_in_region_list(source, osm_data):
    print(source)
    print(osm_data)
    internal_name = None
    for key in ["name:pl", "name:en", "name"]:
        if key in osm_data and osm_data[key] != None:
            internal_name = osm_data[key]
            break
        else:
            print(osm_data["name"], "/", osm_data["name:en"], " has no", key, "tag")
    extra_names = [osm_data.get("name:en"), osm_data.get("name:pl")]
    shown_extra_names = []
    blocked_names = [None, osm_data["name"]]
    for name in extra_names:
        if name not in blocked_names:
            shown_extra_names.append(name)
    website_main_title_part = osm_data["name"]
    if len(shown_extra_names) > 0:
        website_main_title_part += "(" + ", ".join(shown_extra_names) + ")"
    if "extra_part_of_name" in source:
        internal_name = source["extra_part_of_name"] + ": " + internal_name
        website_main_title_part = source["extra_part_of_name"] + ": " + website_main_title_part

    region_data = {
        "internal_region_name": internal_name,
        "website_main_title_part": website_main_title_part,
        "merged_output": source["parent"],
        "identifier": {'wikidata': osm_data["wikidata"]},
        "language_code": source['language_code'],
        "requested_by": source['requested_by'],
        }
    #return "-" + yaml.dump(region_data)
    return "- {internal_region_name: '" + internal_name + "', website_main_title_part: '" + website_main_title_part + "', merged_output: '" + source["parent"] + "', identifier: {'wikidata': '" + osm_data["wikidata"] + "'}, language_code: '" + source['language_code'] + "', requested_by: '" + source["requested_by"] + "'}"

main()