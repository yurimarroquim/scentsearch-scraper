"""
dedup_geral.py — Detecta e mescla entradas duplicadas no catálogo completo.

Uso:
    python3 dedup_geral.py                    # dry-run: mostra grupos duplicados
    python3 dedup_geral.py --apply            # executa as mesclagens
    python3 dedup_geral.py --threshold 90     # ajusta similaridade mínima (padrão: 95)
    python3 dedup_geral.py --limit 30         # limita grupos exibidos no dry-run
"""

import os, re, sys, argparse, time
from collections import defaultdict
from difflib import SequenceMatcher

DEDUP_CHECKPOINT = os.path.join(os.path.dirname(__file__), "dedup_checkpoint.txt")

# Corrige SSL no Windows: httpx 0.28+ não usa ssl module, precisa de verify=False no transport
import httpx
_orig_client_init = httpx.Client.__init__
def _patched_client_init(self, *args, **kwargs):
    kwargs.setdefault("verify", False)
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_client_init

try:
    from rapidfuzz import fuzz as _fuzz
    def similarity(a, b):
        return _fuzz.token_sort_ratio(a, b)
except ImportError:
    def similarity(a, b):
        return SequenceMatcher(None, a, b).ratio() * 100

from supabase import create_client


def _sb_retry(fn, max_retries=5, swallow=False):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if swallow:
                return
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    ⚠️  Erro de rede (tentativa {attempt+1}/{max_retries}), aguardando {wait}s: {e}")
                time.sleep(wait)
            else:
                raise

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

CONC_MAP = {
    # ordem importa: "edp" deve vir antes de "parfum" para "eau de parfum" não
    # ser capturado pelo \bparfum\b genérico e criar buckets errados
    "edp":    [r"eau\s+de\s+parfum", r"\bedp\b"],
    "edt":    [r"eau\s+de\s+toilette", r"\bedt\b"],
    "edc":    [r"eau\s+de\s+cologne", r"\bedc\b"],
    "parfum": [r"\bparfum\b", r"\bextrait\b", r"\belixir\b"],
    "body":   [r"\bbody\s+splash\b", r"\bbody\s+mist\b"],
}

STRIP_WORDS = [
    r"\bperfume\b", r"\bperfumes\b",
    r"\bdesodorante\b", r"\bcolônia\b", r"\bcolonia\b",
    r"\bspray\b", r"\broller\s*ball?\b",
    r"\bfeminino\b", r"\bfeminina\b", r"\bmasculino\b", r"\bmasculina\b",
    r"\bunissex\b", r"\bunisex\b", r"\bfem\b", r"\bmasc\b",
    r"\blacrado\b", r"\boriginal\b", r"\bimportado\b",
    r"\bluxury\s+collection\b", r"\bcollection\b", r"\bexclusive\b",
    r"eau\s+de\s+parfum", r"eau\s+de\s+toilette", r"eau\s+de\s+cologne",
    r"\bextrait\s+de\s+parfum\b", r"\bextrait\b",
    r"\bparfum\b", r"\bedp\b", r"\bedt\b", r"\bedc\b",
    r"\d+\s*ml\b",
    # prefixos de decant — não fazem parte do nome do produto
    r"\bdecant(ã?o)?\b", r"\bno\s+frasco\b", r"\bamostras?\b",
]

GENDER_PAT = [
    ("f", [r"\bfeminino\b", r"\bfeminina\b", r"\bfor\s+her\b", r"\bwomen\b", r"\bfem\b"]),
    ("m", [r"\bmasculino\b", r"\bmasculina\b", r"\bfor\s+him\b", r"\bmen\b", r"\bmasc\b"]),
    ("u", [r"\bunissex\b", r"\bunisex\b"]),
]


def get_concentration(nome):
    t = nome.lower()
    for conc, pats in CONC_MAP.items():
        for p in pats:
            if re.search(p, t):
                return conc
    return "?"


def get_volume(nome):
    m = re.search(r"(\d+)\s*ml", nome, re.I)
    return int(m.group(1)) if m else 0


def get_gender(nome):
    t = nome.lower()
    for g, pats in GENDER_PAT:
        for p in pats:
            if re.search(p, t):
                return g
    return "?"


def get_base(marca, nome):
    """Remove marca (início e fim), volume, concentração, gênero e palavras genéricas."""
    t = nome.lower()
    marca_esc = re.escape(marca.lower().strip())
    t = re.sub(r"^" + marca_esc + r"\s*[-–]?\s*", "", t)
    t = re.sub(r"\s*[-–]?\s*" + marca_esc + r"\s*$", "", t)
    for pat in STRIP_WORDS:
        t = re.sub(pat, " ", t, flags=re.I)
    t = re.sub(r"\b\d+\b", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ---------------------------------------------------------------------------
# Fetch paginado
# ---------------------------------------------------------------------------

def fetch_all():
    print("Carregando catálogo do Supabase...")
    rows = []
    offset, page = 0, 1000
    while True:
        batch = (
            sb.table("perfumes")
            .select("id,marca,nome,tipo")
            .order("id")
            .limit(page)
            .offset(offset)
            .execute()
            .data
        )
        if not batch:
            break
        rows.extend(batch)
        print(f"  {len(rows):,} carregados...", end="\r")
        if len(batch) < page:
            break
        offset += page
    print(f"  Total: {len(rows):,} perfumes        ")
    return rows


# ---------------------------------------------------------------------------
# Detecção de duplicatas
# ---------------------------------------------------------------------------

def has_different_numbers(nome_a, nome_b):
    """Retorna True se os nomes têm números distintos — ex: 'Collection 009' vs 'Collection 008'."""
    nums_a = set(re.findall(r'\b\d+\b', nome_a))
    nums_b = set(re.findall(r'\b\d+\b', nome_b))
    return bool(nums_a and nums_b and nums_a != nums_b)


def has_unique_words(base_a, base_b):
    """Retorna True se os produtos têm nomes distintos após normalização.

    Bloqueia quando:
    - Ambas as bases têm palavras exclusivas (ex: "Unlimited" vs "Untamed")
    - Qualquer base tem 2+ palavras exclusivas (ex: "Pour Homme" extra = produto diferente)

    Tolera diferença de 1 palavra para absorver ruído de normalização (ex: marca escapando).
    """
    words_a = set(re.findall(r'\b\w{4,}\b', base_a))
    words_b = set(re.findall(r'\b\w{4,}\b', base_b))
    only_a = words_a - words_b
    only_b = words_b - words_a
    return bool(
        (only_a and only_b)         # ambos têm palavras exclusivas
        or len(only_a) >= 2         # um tem 2+ palavras extras (ex: "pour homme")
        or len(only_b) >= 2
    )


def find_duplicates(rows, threshold):
    buckets = defaultdict(list)
    for r in rows:
        marca = (r["marca"] or "").strip()
        nome  = r["nome"] or ""
        key   = (
            marca.lower(),
            get_concentration(nome),
            get_volume(nome),
            get_gender(nome),
            r.get("tipo") or "perfume",  # nunca mescla frasco com decant
        )
        base = get_base(marca, nome)
        buckets[key].append({**r, "_base": base})

    dup_groups = []
    for items in buckets.values():
        if len(items) < 2:
            continue
        used = [False] * len(items)
        for i in range(len(items)):
            if used[i]:
                continue
            group = [items[i]]
            used[i] = True
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                a = items[i]["_base"]
                b = items[j]["_base"]
                if has_different_numbers(items[i]["nome"], items[j]["nome"]):
                    continue
                if has_unique_words(a, b):
                    continue
                sim = similarity(a, b) if (a and b) else 0
                if sim >= threshold:
                    group.append(items[j])
                    used[j] = True
            if len(group) >= 2:
                dup_groups.append(group)

    return dup_groups


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def fetch_price_counts(all_ids):
    """Busca contagem de preços para todos os IDs em uma única query."""
    counts = {}
    ids = list(all_ids)
    # UUIDs são longos — URL explode com >100 ids por vez
    for i in range(0, len(ids), 100):
        batch = ids[i:i+100]
        r = sb.table("precos").select("perfume_id").in_("perfume_id", batch).execute()
        for row in r.data:
            pid = row["perfume_id"]
            counts[pid] = counts.get(pid, 0) + 1
    return counts


def print_group(group, price_counts):
    scored = [(price_counts.get(r["id"], 0), -len(r["nome"]), i, r)
              for i, r in enumerate(group)]
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    print(f"\n  KEEPER ({scored[0][0]} preços): {scored[0][3]['nome']}")
    for s in scored[1:]:
        print(f"    DUP  ({s[0]} preços): {s[3]['nome']}")


def build_keeper_map(groups, price_counts):
    """Retorna (keeper_map, all_dup_ids) sem tocar no banco."""
    keeper_map = {}   # dup_id -> keeper_id
    all_dup_ids = []
    for g in groups:
        scored = [(price_counts.get(r["id"], 0), -len(r["nome"]), i, r)
                  for i, r in enumerate(g)]
        scored.sort(key=lambda x: (-x[0], x[1], x[2]))
        keeper = scored[0][3]
        for s in scored[1:]:
            keeper_map[s[3]["id"]] = keeper["id"]
            all_dup_ids.append(s[3]["id"])
    return keeper_map, all_dup_ids


def apply_all_batch(keeper_map, all_dup_ids):
    """Executa todas as mesclagens em 3 fases em lote — mínimo de round-trips."""

    print(f"\n{len(all_dup_ids)} duplicatas a remover. Executando em lotes...")

    # ── Fase 1: notas_olfativas ──────────────────────────────────────────────
    print("Fase 1/3: notas olfativas...")

    # Descobre quais perfumes (keepers + dups) têm notas
    all_ids_notas = list(set(all_dup_ids) | set(keeper_map.values()))
    tem_notas = set()
    for i in range(0, len(all_ids_notas), 100):
        b = all_ids_notas[i:i+100]
        r = _sb_retry(lambda b=b: sb.table("notas_olfativas").select("perfume_id").in_("perfume_id", b).execute())
        tem_notas.update(row["perfume_id"] for row in r.data)

    # Para cada keeper sem notas: migrar notas do PRIMEIRO dup que tiver (1 por keeper)
    # Para dups adicionais com notas do mesmo keeper: deletar
    keeper_migrado = set()
    dups_to_migrate = {}   # dup_id -> keeper_id (um por keeper)
    dups_to_delete_notes = []

    for d in all_dup_ids:
        if d not in tem_notas:
            continue
        k = keeper_map[d]
        if k in tem_notas or k in keeper_migrado:
            dups_to_delete_notes.append(d)
        else:
            dups_to_migrate[d] = k
            keeper_migrado.add(k)

    # Deleta notas conflitantes em lote
    for i in range(0, len(dups_to_delete_notes), 100):
        b = dups_to_delete_notes[i:i+100]
        _sb_retry(lambda b=b: sb.table("notas_olfativas").delete().in_("perfume_id", b).execute())

    # Migra um dup por keeper (update individual — evita unique constraint)
    for dup_id, keeper_id in dups_to_migrate.items():
        _sb_retry(lambda d=dup_id, k=keeper_id: sb.table("notas_olfativas").update({"perfume_id": k}).eq("perfume_id", d).execute())

    print(f"  ✓ {len(dups_to_migrate)} notas migradas | {len(dups_to_delete_notes)} conflitos deletados")

    # ── Fase 2: precos ───────────────────────────────────────────────────────
    print("Fase 2/3: preços...")
    all_ids = list(set(all_dup_ids) | set(keeper_map.values()))
    precos_by_perfume = {}  # perfume_id -> {loja: preco_id}
    for i in range(0, len(all_ids), 100):
        b = all_ids[i:i+100]
        r = _sb_retry(lambda b=b: sb.table("precos").select("id,perfume_id,loja").in_("perfume_id", b).execute())
        for row in r.data:
            precos_by_perfume.setdefault(row["perfume_id"], {})[row["loja"]] = row["id"]

    conflict_ids = []
    keeper_to_safe = defaultdict(list)
    for dup_id in all_dup_ids:
        keeper_id = keeper_map[dup_id]
        keeper_stores = set(precos_by_perfume.get(keeper_id, {}).keys())
        for loja, preco_id in precos_by_perfume.get(dup_id, {}).items():
            if loja in keeper_stores:
                conflict_ids.append(preco_id)
            else:
                keeper_to_safe[keeper_id].append(preco_id)

    for i in range(0, len(conflict_ids), 100):
        b = conflict_ids[i:i+100]
        _sb_retry(lambda b=b: sb.table("precos").delete().in_("id", b).execute())

    migrated_precos = 0
    for keeper_id, preco_ids in keeper_to_safe.items():
        for i in range(0, len(preco_ids), 100):
            b = preco_ids[i:i+100]
            _sb_retry(lambda b=b, k=keeper_id: sb.table("precos").update({"perfume_id": k}).in_("id", b).execute())
            migrated_precos += len(b)
    print(f"  ✓ {migrated_precos} preços migrados | {len(conflict_ids)} conflitos deletados")

    # ── Fase 3: deletar perfumes duplicados ──────────────────────────────────
    print("Fase 3/3: deletando perfumes duplicados...")
    for i in range(0, len(all_dup_ids), 100):
        b = all_dup_ids[i:i+100]
        _sb_retry(lambda b=b: sb.table("perfumes").delete().in_("id", b).execute())
    print(f"  ✓ {len(all_dup_ids)} perfumes duplicados removidos")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply",     action="store_true", help="Executa as mesclagens")
    parser.add_argument("--threshold", type=int, default=95, help="Similaridade mínima (padrão: 95)")
    parser.add_argument("--limit",     type=int, default=0,  help="Limita grupos no dry-run (0=todos)")
    args = parser.parse_args()

    rows   = fetch_all()
    groups = find_duplicates(rows, threshold=args.threshold)

    print(f"\n{'='*60}")
    print(f"{len(groups)} grupos duplicados encontrados (threshold={args.threshold}%)")
    print(f"{'='*60}")

    # Batch: busca contagem de preços para todos os perfumes de uma vez
    all_ids = {r["id"] for g in groups for r in g}
    print(f"Buscando contagem de preços para {len(all_ids):,} perfumes...")
    price_counts = fetch_price_counts(all_ids)

    if args.apply:
        keeper_map, all_dup_ids = build_keeper_map(groups, price_counts)
        apply_all_batch(keeper_map, all_dup_ids)
        if os.path.exists(DEDUP_CHECKPOINT):
            os.remove(DEDUP_CHECKPOINT)
    else:
        shown = 0
        for g in groups:
            if args.limit and shown >= args.limit:
                print(f"\n  ... (limitado a {args.limit} grupos, use --limit 0 para ver todos)")
                break
            print_group(g, price_counts)
            shown += 1

    print(f"\n{'='*60}")
    if args.apply:
        print("✅ Concluído.")
    else:
        print("[DRY-RUN] Nenhuma alteração feita. Rode com --apply para executar.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
