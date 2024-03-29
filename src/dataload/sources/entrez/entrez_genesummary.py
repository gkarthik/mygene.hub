from entrez_base import GeneSummaryParser

__metadata__ = {
    '__collection__' : 'entrez_genesummary',
    'structure': {'summary': unicode},
}

def load_genedoc(self):
    gene2summary = GeneSummaryParser().load()
    return gene2summary

def get_mapping(self):
    mapping = {
        "summary": {"type": "string",
                    "boost": 0.5},      #downgrade summary field.
    }
    return mapping
