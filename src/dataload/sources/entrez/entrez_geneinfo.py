from mongokit import OR
from entrez_base import GeneInfoParser

structure = {'taxid': int,
             'entrezgene': int,
             'alias': OR(unicode, list)
             }
string_fields = ['name', 'symbol', 'map_location', 'type_of_gene',
                 'HGNC', 'HPRD', 'MIM', 'MGI', 'RATMAP', 'RGD', 'FLYBASE',
                 'WormBase', 'TAIR', 'ZFIN', 'Xenbase']
for field in string_fields:
    structure[field] = unicode

__metadata__ = {
    '__collection__' : 'entrez_geneinfo',
    'structure': structure,
    'required_fields' : ['taxid', 'entrezgene', 'symbol'],
    'ENTREZ_GENEDOC_ROOT' : True
}

def load_genedoc(self):
    genedoc_d = GeneInfoParser().load()
    return genedoc_d

def get_mapping(self):
    mapping = {
        "entrezgene": {"type": "long",
                       "boost": 10.0},
        "taxid":  {"type": "integer",
                   "include_in_all": False},
        "alias":  {"type": "string"},
        "name":   {"type": "string",
                   "boost": 0.8},    #downgrade name field a little bit
        "symbol": {"type": "string",
                   "analyzer": "string_lowercase",
                   "boost": 5.0},

        #do not index map_location and type_of_gene
        "map_location": {"index": "no",
                         "type": "string",
                         "include_in_all": False},
        "type_of_gene": {"index": "no",
                         "type": "string",
                         "include_in_all": False},

        #convert index_name to lower-case, and excluded from "_all"
        "HGNC": {"type": "string",              #1771
                 "index": "not_analyzed",
                 "include_in_all": False,
                 "index_name": 'hgnc'},
        "HPRD": {"type": "string",              #00310
                 "index": "not_analyzed",
                 "include_in_all": False,
                 "index_name": 'hprd'},
        "MIM":  {"type": "string",              #116953
                 "index": "not_analyzed",
                 "include_in_all": False,
                 "index_name": 'mim'},
        "MGI":  {"type": "string",              #MGI:104772
                 "index": "not_analyzed",
                 "include_in_all": False,
                 "index_name": 'mgi'},
        "RATMAP":{"type": "string",
                 "index": "not_analyzed",
                 "include_in_all": False,
                 "index_name": 'ratmap'},
        "RGD":   {"type": "string",             #70486
                 "index": "not_analyzed",
                 "include_in_all": False,
                 "index_name": 'rgd'},
        "FLYBASE":{"type": "string",            #FBgn0004107
                 "analyzer": "string_lowercase",
                 "include_in_all": False,
                 "index_name": 'flybase'},
        "WormBase":  {"type": "string",         #WBGene00000871
                 "analyzer": "string_lowercase",
                 "include_in_all": False,
                 "index_name": 'wormbase'},
        "TAIR":  {"type": "string",             #AT3G48750
                 "analyzer": "string_lowercase",
                 "include_in_all": False,
                 "index_name": 'tair'},
        "ZFIN":  {"type": "string",             #ZDB-GENE-040426-2741
                 "analyzer": "string_lowercase",
                 "include_in_all": False,
                 "index_name": 'zfin'},
        "Xenbase":{"type": "string",
                 "analyzer": "string_lowercase",
                 "include_in_all": False,
                 "index_name": 'xenbase'},
    }
    return mapping

