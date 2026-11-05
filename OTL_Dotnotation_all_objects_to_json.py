#Dit script gebruikt de OTL-MOW converter om een dotnotatie representatie te maken van alle attributen de OTL.
#Deze worden weggeschreven naar een .ttl file
#Dit geeft per object de dotnotatie-attribuutnaam en bijhorend datatype.

import importlib
import json
from sqlite3 import Error
from os.path import exists
import ctypes
import inspect
import pkgutil

#FUNCTIES
def load_OTL_modules():
    """Laad de OTL-MOW model modules in zodat deze gebruikt kunnen worden voor het ophalen van de attributen"""

    try:
        #NODIGE MODULES UIT OTLMOW CONVERTER INLADEN
        from otlmow_converter.DotnotationDictConverter import DotnotationDictConverter
        from otlmow_converter.DotnotationHelper import DotnotationHelper
        
        #NODIGE MODULES UIT OTLMOW MODEL INLADEN
        from otlmow_model.OtlmowModel.BaseClasses.KeuzelijstField import KeuzelijstField
        from otlmow_model.OtlmowModel.BaseClasses.StringField import StringField
        from otlmow_model.OtlmowModel.BaseClasses.BooleanField import BooleanField
        from otlmow_model.OtlmowModel.BaseClasses.FloatOrDecimalField import FloatOrDecimalField
        from otlmow_model.OtlmowModel.BaseClasses.NonNegIntegerField import NonNegIntegerField
        from otlmow_model.OtlmowModel.BaseClasses.IntegerField import IntegerField
        from otlmow_model.OtlmowModel.BaseClasses.OTLObject import OTLAttribuut
        from otlmow_model.OtlmowModel.BaseClasses.OTLObject import dynamic_create_instance_from_uri as instancecreator

    except Exception as e:
        print(f"Fout bij inladen van libraries: {e}")

    return instancecreator, DotnotationDictConverter, DotnotationHelper, KeuzelijstField, StringField, BooleanField, FloatOrDecimalField, NonNegIntegerField, IntegerField, OTLAttribuut

def attribute_info_to_dict(obj, attribute):
    """verzamelt de info van het attribuut (in dotnatatie) in een dict"""

    attribuutdict = {} # een dict per dotnotatie-attribuut

    #SPECIALE ATTRIBUTEN
    if attribute == "typeURI": #kan geen attr ophalen voor typeURI
        #attr = getattr(obj,"_typeURI")
        attribuutdict["attribuutdefinitie"] = "De URI van het object"
        attribuutdict["OTL_datatype_attribuut"] = "StringField"
        attribuutdict["civil3D_datatype_attribuut"] = "Text"
        attribuutdict["civil3D_default_value"] = obj.typeURI
        attribuutdict["dotnotatie_attribuutnaam"] = attribute

    elif attribute == "geometry": 
        attribuutdict = {} #Geometrie attribuut niet nodig in civil3D, 

    #NORMALE ATTRIBUTEN
    else:
        #ATTRIBUUTNAAM
        attribuutdict["dotnotatie_attribuutnaam"] = attribute
        attr = DotnotationHelper.get_attribute_by_dotnotation(obj,attribute,waarde_shortcut=False) #haalt het attribuut-object op
        attr_ws = DotnotationHelper.get_attribute_by_dotnotation(obj,attribute,waarde_shortcut=True)

        #DEFINTIE
        attribuutdict["attribuutdefinitie"] = (attr.definition[:250] + '..') if len(attr.definition) > 250 else attr.definition
        
        #DATATYPES
        OTL_datatype = attr_ws.field
        attribuutdict["OTL_datatype_attribuut"] = OTL_datatype.naam
            
        #Civil3D DATATYPE & DEFAULT VALUE(civil3D datatypes)
        if OTL_datatype.naam == "String":
            attribuutdict["civil3D_datatype_attribuut"] = "Text"
            attribuutdict["civil3D_default_value"] = ""
        elif OTL_datatype.naam == "Decimal" or OTL_datatype.naam == "Float":
            attribuutdict["civil3D_datatype_attribuut"] = "Real"
            attribuutdict["civil3D_default_value"] = -999999999.000000
        elif OTL_datatype.naam == "NonNegInteger" or OTL_datatype.naam == "Integer":
            attribuutdict["civil3D_datatype_attribuut"] = "Integer"
            attribuutdict["civil3D_default_value"] = -999999999
        elif OTL_datatype.naam == "Boolean":
            if attribute == "isActief":
                attribuutdict["civil3D_datatype_attribuut"] = 'keuzelijst'
                attribuutdict["civil3D_default_value"] = 'True'
                attribuutdict["keuzelijstopties"] = ['True','False','-']
                attribuutdict["keuzelijstnaam"] = 'booleanlijst-true-default'
            else:
                attribuutdict["civil3D_datatype_attribuut"] = 'keuzelijst'
                attribuutdict["civil3D_default_value"] = '-'
                attribuutdict["keuzelijstopties"] = ['-','True','False']
                attribuutdict["keuzelijstnaam"] = 'booleanlijst'

        #KEUZELIJSTOPTIES
        elif OTL_datatype.naam.startswith("Kl"):
            attribuutdict["civil3D_datatype_attribuut"] = 'keuzelijst'
            attribuutdict["civil3D_default_value"] = '-'
            keuzelijstopties = ["-"] #Default value voor keuzelijst moet in lijst voorkomen
            for i, k in enumerate(attr.field.options.keys()):
                keuzelijstopties.append(k)
            attribuutdict["keuzelijstopties"] = keuzelijstopties
            attribuutdict["keuzelijstnaam"] = str(attr.field.naam)       
        else: #DateField, URIField, ..
            attribuutdict["civil3D_datatype_attribuut"] = "Text"
            attribuutdict["civil3D_default_value"] = ""

    return attribuutdict

def create_psetnaam(obj, urilijst):
    """Maakt de unieke propertysetnaam voor een object"""

    #Naam en soort van de klasse
    objectnaam = obj.__class__.__name__
    objectsoort = obj.typeURI.split('/')[-1].split('#')[0] #objectsoort afleiden uit typeURI

    #Deprecation label toevoegen
    if hasattr(obj, 'deprecated_version'):
        depr = "_DEPR-" + str(obj.deprecated_version)
    else:
        depr = ""

    #Controle of naam reeds voorkomt
    if sum(s.endswith('#' + objectnaam) for s in urilijst) == 1:
        propertysetnaam = "OTL_" + objectnaam + depr
    else: 
        propertysetnaam = "OTL_" + objectnaam + "_" + objectsoort + depr 

    return propertysetnaam

def get_dotnotation(obj):
    """creer de dotnotatie weergave voor de attributen"""
    
    obj.fill_with_dummy_data() #Vul het object met dummy data, zodat deze bruikbaar is voor dotnotationdict

    #Workaround voor ListOfList error bij dotnotatie creatie:
    if obj.typeURI == "https://wegenenverkeer.data.vlaanderen.be/ns/implementatieelement#Toegangsprocedure": 
        obj.bijlage = None
    if obj.typeURI == "https://wegenenverkeer.data.vlaanderen.be/ns/onderdeel#HeeftBetrokkene":
        obj.specifiekeContactinfo = None

    try:
        d_dict = DotnotationDictConverter.to_dict(obj) #Vertaal alle attributen naar dotnotatie
    except Error as e:
        print(f"Dotnotatie aanmaken gefaald voor {obj.__class__.__name__}: {e}")
        pass

    return d_dict
    
def get_all_OTL_uris():
    """Haalt alle OTL uris op uit het OTLMOW model voor onderdelen en installaties"""

    # 1. Importeer de directory (package). 
    import otlmow_model.OtlmowModel.Classes.Onderdeel as onderdeel_directory
    import otlmow_model.OtlmowModel.Classes.Installatie as installatie_directory
    import otlmow_model.OtlmowModel.Classes.ImplementatieElement as implementatie_directory

    type_uris = []

    # 2. Loop door alle Python-bestanden (submodules) in de directory
    for dir in [onderdeel_directory, installatie_directory, implementatie_directory]:
        for module_info in pkgutil.iter_modules(dir.__path__):
            volledige_module_naam = f"{dir.__name__}.{module_info.name}"
            
            try:
                # Importeer de submodule dynamisch
                module = importlib.import_module(volledige_module_naam)
                
                # 3. Gebruik inspect om alle klasses binnen deze submodule te vinden
                for klasse_naam, klasse_object in inspect.getmembers(module, inspect.isclass):
                    
                    # Controleer of de klasse daadwerkelijk in deze specifieke module is 
                    if klasse_object.__module__ == module.__name__:
                        
                        # 4. Controleer of de klasse het attribuut 'typeURI' bezit
                        if hasattr(klasse_object, 'typeURI'):
                            # Voeg de waarde toe aan de lijst
                            type_uris.append(klasse_object.typeURI)

            except ImportError as e:
                print(f"Waarschuwing: Kon module {volledige_module_naam} niet importeren. ({e})")

    # Haal alle duplicaten eruit voor een schone lijst
    unieke_type_uris = list(set(type_uris))

    return unieke_type_uris

def OTL_attr_to_dot():
    """Gebruikt de OTLMOW model om alle attributen uit de OTL te vertalen naar een tll met dotnotatie"""
    try:
        dictlijst = [] 

        urilijst = get_all_OTL_uris() #haal een lijst van object uris op uit de OTL onderdelen en installaties

        for uri in urilijst:
            try:
                obj = instancecreator(uri) #Instantieer de klasse via het OTLMOW model
                dotnotatie_attributen = get_dotnotation(obj) #Haalt alle dotnotatie attributen op voor het object 
            except Exception as e:
                print(f"Kan object niet instantiëren via URI {uri}: {e}")
                continue

            #Verzamel info over het onderdeel (of installatie, implemenatieelement, ...)
            onderdeeldict = {} #een dict om alle info voor een bepaalde propertyset in te verzamelen
            onderdeeldict["propertysetnaam"] = create_psetnaam(obj, urilijst) #creert een unieke propertysetnaam
            onderdeeldict["definitie"] = (obj.__doc__[:250] + '..') if len(obj.__doc__) > 250 else obj.__doc__
            onderdeeldict["typeURI"] = obj.typeURI
            onderdeeldict["attributen"] = []

            #Verzamel info per attribuut
            for attribute in dotnotatie_attributen:
                attribuutdict = attribute_info_to_dict(obj,attribute)
                if attribuutdict: #Voegt enkel toe aan attributenlijst in dict als er een attribuutdict werd gemaakt.
                    onderdeeldict["attributen"].append(attribuutdict) #Voeg de attribuutinfo toe aan de dict voor dit onderdeel

            dictlijst.append(onderdeeldict)

    except Exception as e:
        print(f"Fout bij omzetten van de OTL data: {e}")   

    return dictlijst

def OTL_to_json(OTLinfodict, json_filename):
    """Schrijft de dict met OTL info weg naar een json file"""

    try:
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(OTLinfodict, f, ensure_ascii=False, indent=4, sort_keys=True)

        print(f"JSON file '{json_filename}' succesvol aangemaakt.")

    except Exception as e:
        print(f"Fout bij schrijven van de json file: {e}")

#UITVOEREN

#1. modules inladen
instancecreator, DotnotationDictConverter, DotnotationHelper, KeuzelijstField, StringField, BooleanField, FloatOrDecimalField, NonNegIntegerField, IntegerField, OTLAttribuut = load_OTL_modules()
#2. OTL info naar dict omzetten
OTLinfodict = OTL_attr_to_dot()   
#3. dict naar json file schrijven
OTL_to_json(OTLinfodict, "OTL_Dotnotation_all_objects.json")
