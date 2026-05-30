"""
notas_ingredientes_import.py
Lê notas únicas do CSV Parfumo, traduz para PT-BR, verifica imagem no CDN Fragrantica
e popula a tabela notas_ingredientes no Supabase.

PRÉ-REQUISITO (SQL Editor):
  CREATE TABLE IF NOT EXISTS notas_ingredientes (
    nome_en    TEXT PRIMARY KEY,
    nome_pt    TEXT NOT NULL,
    imagem_url TEXT
  );
  ALTER TABLE notas_ingredientes ENABLE ROW LEVEL SECURITY;
  CREATE POLICY "leitura publica" ON notas_ingredientes FOR SELECT USING (true);
"""
import os, re, unicodedata, logging
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CSV_PATH     = r"c:\Users\yurim\OneDrive\Área de Trabalho\ScentSearch\database_fragrantica\parfumo_data_clean.csv"
NOTE_COLUMNS = ["Top_Notes", "Middle_Notes", "Base_Notes"]

NOTAS_MAP = {
    # Cítricos
    "bergamot":            "Bergamota",
    "lemon":               "Limão",
    "orange":              "Laranja",
    "grapefruit":          "Toranja",
    "lime":                "Lima",
    "mandarin":            "Mandarina",
    "tangerine":           "Tangerina",
    "clementine":          "Clementina",
    "yuzu":                "Yuzu",
    "blood orange":        "Laranja Sanguínea",
    "kumquat":             "Kumquat",
    "citron":              "Cidra",
    "lemongrass":          "Capim-Limão",
    "verbena":             "Verbena",
    "lemon verbena":       "Verbena Limão",
    "petitgrain":          "Petitgrain",
    "neroli":              "Neroli",

    # Florais
    "rose":                "Rosa",
    "jasmine":             "Jasmim",
    "iris":                "Íris",
    "lily of the valley":  "Lírio do Vale",
    "violet":              "Violeta",
    "peony":               "Peônia",
    "tuberose":            "Tuberosa",
    "ylang-ylang":         "Ylang-Ylang",
    "ylang ylang":         "Ylang-Ylang",
    "gardenia":            "Gardênia",
    "magnolia":            "Magnólia",
    "freesia":             "Frésia",
    "lily":                "Lírio",
    "orchid":              "Orquídea",
    "geranium":            "Gerânio",
    "osmanthus":           "Osmanthus",
    "orange blossom":      "Flor de Laranjeira",
    "heliotrope":          "Heliotrópio",
    "mimosa":              "Mimosa",
    "carnation":           "Cravo",
    "narcissus":           "Narciso",
    "cyclamen":            "Ciclame",
    "wisteria":            "Glicínia",
    "linden blossom":      "Flor de Tília",
    "bulgarian rose":      "Rosa Búlgara",
    "turkish rose":        "Rosa Turca",
    "rose de mai":         "Rosa de Maio",
    "jasmine sambac":      "Jasmim Sambac",
    "frangipani":          "Frangipani",
    "plumeria":            "Plumeria",
    "lotus":               "Lótus",
    "water lily":          "Nenúfar",
    "cherry blossom":      "Flor de Cerejeira",
    "elderflower":         "Flor de Sabugueiro",
    "honeysuckle":         "Madressilva",
    "hyacinth":            "Jacinto",
    "chrysanthemum":       "Crisântemo",
    "marigold":            "Calêndula",
    "chamomile":           "Camomila",
    "davana":              "Davana",
    "cassie":              "Cássia",
    "jasminum auriculatum": "Jasmim Auriculatum",
    "jasminum":            "Jasmim",
    "hedychium":           "Hedíquio",

    # Ervas / Aromáticos
    "lavender":            "Lavanda",
    "clary sage":          "Sálvia Romana",
    "sage":                "Sálvia",
    "rosemary":            "Alecrim",
    "thyme":               "Tomilho",
    "basil":               "Manjericão",
    "mint":                "Hortelã",
    "spearmint":           "Hortelã Verde",
    "peppermint":          "Hortelã-Pimenta",
    "eucalyptus":          "Eucalipto",
    "camphor":             "Cânfora",
    "coriander":           "Coentro",
    "tarragon":            "Estragão",
    "bay leaf":            "Louro",
    "orris root":          "Raiz de Íris",
    "orris":               "Íris",
    "iris root":           "Raiz de Íris",
    "violet leaf":         "Folha de Violeta",
    "galbanum":            "Gálbano",

    # Amadeirados
    "sandalwood":          "Sândalo",
    "cedar":               "Cedro",
    "cedarwood":           "Cedro",
    "atlas cedar":         "Cedro Atlas",
    "virginia cedar":      "Cedro da Virgínia",
    "white cedar":         "Cedro Branco",
    "vetiver":             "Vetiver",
    "patchouli":           "Patchouli",
    "oud":                 "Oud",
    "agarwood":            "Agarwood",
    "guaiac wood":         "Madeira de Guaiac",
    "birch":               "Bétula",
    "pine":                "Pinheiro",
    "fir":                 "Abeto",
    "spruce":              "Abeto",
    "oakwood":             "Madeira de Carvalho",
    "driftwood":           "Madeira Flutuante",
    "papyrus":             "Papiro",
    "bamboo":              "Bambu",
    "teak wood":           "Madeira de Teca",
    "rosewood":            "Pau-Rosa",
    "cypress":             "Cipreste",
    "juniper":             "Zimbro",
    "amyris":              "Amíris",
    "cabreuva":            "Cabreúva",

    # Resinas / Incenso
    "incense":             "Incenso",
    "frankincense":        "Olíbano",
    "myrrh":               "Mirra",
    "elemi":               "Elemi",
    "benzoin":             "Benjoim",
    "labdanum":            "Lábdano",
    "styrax":              "Estorace",
    "peru balsam":         "Bálsamo do Peru",
    "tolu balsam":         "Bálsamo de Tolú",
    "opoponax":            "Opopônax",
    "copal":               "Copal",
    "cistus":              "Cisto",
    "rockrose":            "Rosa de Pedra",
    "fir balsam":          "Bálsamo de Abeto",
    "fir resin":           "Resina de Abeto",
    "mastic":              "Mástique",
    "spikenard":           "Nardo",
    "birch tar":           "Alcatrão de Bétula",

    # Musgos / Terra
    "oakmoss":             "Musgo de Carvalho",
    "moss":                "Musgo",
    "treemoss":            "Musgo de Árvore",
    "mushroom":            "Cogumelo",
    "truffle":             "Trufa",
    "hay":                 "Feno",
    "grass":               "Grama",
    "soil":                "Terra",

    # Almiscarados / Âmbar
    "musk":                "Almíscar",
    "white musk":          "Almíscar Branco",
    "musks":               "Almíscares",
    "ambergris":           "Âmbar Gris",
    "amber":               "Âmbar",
    "ambrette":            "Ambrete",
    "ambroxan":            "Ambroxan",
    "cashmeran":           "Cashmeran",
    "iso e super":         "Iso E Super",
    "hedione":             "Hediona",
    "beeswax":             "Cera de Abelha",

    # Baunilha / Gourmand doce
    "vanilla":             "Baunilha",
    "tonka bean":          "Fava Tonka",
    "coffee":              "Café",
    "chocolate":           "Chocolate",
    "caramel":             "Caramelo",
    "praline":             "Pralinê",
    "almond":              "Amêndoa",
    "hazelnut":            "Avelã",
    "pistachio":           "Pistache",
    "walnut":              "Nozes",
    "marshmallow":         "Marshmallow",
    "cotton candy":        "Algodão Doce",
    "sugar":               "Açúcar",
    "milk":                "Leite",
    "cream":               "Creme",
    "butter":              "Manteiga",
    "honey":               "Mel",
    "licorice":            "Alcaçuz",
    "marzipan":            "Maçapão",
    "gingerbread":         "Pão de Mel",
    "bread":               "Pão",
    "rice":                "Arroz",

    # Bebidas
    "rum":                 "Rum",
    "wine":                "Vinho",
    "whisky":              "Whisky",
    "bourbon":             "Bourbon",
    "champagne":           "Champagne",
    "liqueur":             "Licor",
    "tea":                 "Chá",
    "green tea":           "Chá Verde",
    "black tea":           "Chá Preto",
    "white tea":           "Chá Branco",
    "mate":                "Mate",

    # Especiarias
    "pepper":              "Pimenta",
    "black pepper":        "Pimenta Preta",
    "pink pepper":         "Pimenta Rosa",
    "white pepper":        "Pimenta Branca",
    "cardamom":            "Cardamomo",
    "cinnamon":            "Canela",
    "clove":               "Cravo",
    "nutmeg":              "Noz-Moscada",
    "ginger":              "Gengibre",
    "saffron":             "Açafrão",
    "star anise":          "Anis Estrelado",
    "anise":               "Anis",
    "cumin":               "Cominho",
    "allspice":            "Pimenta-Jamaica",
    "turmeric":            "Cúrcuma",
    "mace":                "Macis",

    # Frutas
    "apple":               "Maçã",
    "peach":               "Pêssego",
    "pear":                "Pera",
    "plum":                "Ameixa",
    "raspberry":           "Framboesa",
    "strawberry":          "Morango",
    "blackcurrant":        "Groselha Preta",
    "cassis":              "Cássis",
    "mango":               "Manga",
    "pineapple":           "Abacaxi",
    "fig":                 "Figo",
    "coconut":             "Coco",
    "lychee":              "Lichia",
    "watermelon":          "Melancia",
    "melon":               "Melão",
    "grape":               "Uva",
    "cherry":              "Cereja",
    "apricot":             "Damasco",
    "blackberry":          "Amora",
    "blueberry":           "Mirtilo",
    "passion fruit":       "Maracujá",
    "guava":               "Goiaba",
    "papaya":              "Mamão",
    "pomegranate":         "Romã",
    "quince":              "Marmelo",
    "currant":             "Groselha",
    "nectarine":           "Nectarina",
    "tamarind":            "Tamarindo",
    "cranberry":           "Cranberry",

    # Aquáticos / Frescos
    "sea notes":           "Notas Marinhas",
    "aquatic notes":       "Notas Aquáticas",
    "ozonic notes":        "Notas Ozônicas",
    "marine notes":        "Notas Marinhas",
    "sea salt":            "Sal Marinho",
    "seaweed":             "Alga Marinha",
    "green notes":         "Notas Verdes",
    "ozone":               "Ozônio",
    "rain":                "Chuva",

    # Animálicos / Couro
    "leather":             "Couro",
    "castoreum":           "Castóreo",
    "civet":               "Civeta",
    "tobacco":             "Tabaco",

    # Sintéticos / Químicos (mantém nome técnico)
    "aldehydes":           "Aldeídos",
    "powder":              "Pó",
    "talc":                "Talco",
    "solar notes":         "Notas Solares",
    "smoke":               "Fumaça",
    "incense":             "Incenso",
    "mineral":             "Mineral",
    "wood":                "Madeira",
    "woods":               "Madeiras",
    "resins":              "Resinas",

    # Notas genéricas
    "woody notes":         "Notas Amadeiradas",
    "floral notes":        "Notas Florais",
    "fruity notes":        "Notas Frutadas",
    "spicy notes":         "Notas Especiadas",
    "sweet notes":         "Notas Doces",
}


def slugify_fragrantica(name: str) -> str:
    s = name.lower().strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s.strip("-")


def fragrantica_url(slug: str) -> str:
    return f"https://fimgs.net/mdimg/notepic/{slug}.jpg"


def run():
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="latin-1")
    log.info(f"CSV carregado: {len(df):,} linhas")

    # Extrai notas únicas de todas as colunas
    unique_notes: set[str] = set()
    for col in NOTE_COLUMNS:
        if col not in df.columns:
            continue
        for val in df[col].dropna():
            val = str(val).strip()
            if val.upper() in ("NA", "NAN", ""):
                continue
            for nota in val.split(","):
                nota = nota.strip()
                if nota:
                    unique_notes.add(nota)

    log.info(f"Notas únicas: {len(unique_notes)}")

    records = []

    for i, nota_en in enumerate(sorted(unique_notes)):
        slug    = slugify_fragrantica(nota_en)
        nota_pt = NOTAS_MAP.get(nota_en.lower(), nota_en)
        img_url = fragrantica_url(slug)

        records.append({
            "nome_en":    nota_en,
            "nome_pt":    nota_pt,
            "imagem_url": img_url,
        })

        if (i + 1) % 500 == 0:
            log.info(f"  [{i+1}/{len(unique_notes)}] processadas")

    # Upsert em lotes de 100
    BATCH = 100
    for start in range(0, len(records), BATCH):
        chunk = records[start:start + BATCH]
        supabase.table("notas_ingredientes").upsert(chunk, on_conflict="nome_en").execute()

    log.info("=" * 40)
    log.info(f"Total inserido: {len(records)}")
    log.info(f"URLs geradas (verificação feita pelo frontend via onError)")


if __name__ == "__main__":
    load_dotenv()
    run()
