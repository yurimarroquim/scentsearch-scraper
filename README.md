# ScentSearch Scraper

Sistema completo de scraping de preços de perfumes em Python, com painel de controle web, agendamento automático e integração com WordPress.

## Funcionalidades

- **Scraping automático** de 10 lojas brasileiras de perfumes
- **Armazenamento** em banco de dados SQLite
- **Agendamento diário** configurável via cron
- **Painel web** com FastAPI para monitoramento
- **Integração WordPress** via REST API
- **Modular e extensível** para outros comparadores

## Lojas Suportadas (Fase 1)

| Loja | Slug |
|------|------|
| Época Cosméticos | `epoca` |
| Beleza na Web | `belezanaweb` |
| Amazon Brasil | `amazon` |
| Mercado Livre | `mercadolivre` |
| Sephora Brasil | `sephora` |
| Sieno Perfumaria | `sieno` |
| AAZ Perfumes | `aaz` |
| Shoptime | `shoptime` |
| The King of Parfums | `kingofparfums` |
| Beautybox | `beautybox` |

## Tecnologias

- **Python 3.11+**
- **Playwright** + **BeautifulSoup4** — scraping
- **SQLite** + **SQLAlchemy** — banco de dados
- **FastAPI** + **Jinja2** — painel web
- **APScheduler** — agendamento
- **Requests** — requisições HTTP

## Estrutura do Projeto

```
scentsearch-scraper/
├── config/
│   └── settings.py          # Configurações via .env
├── scrapers/
│   ├── base.py              # Classe base abstrata
│   ├── manager.py           # Gerenciador de scrapers
│   ├── epoca.py             # Época Cosméticos
│   ├── belezanaweb.py       # Beleza na Web
│   ├── amazon.py            # Amazon Brasil
│   ├── mercadolivre.py      # Mercado Livre
│   ├── sephora.py           # Sephora Brasil
│   ├── sieno.py             # Sieno Perfumaria
│   ├── aaz.py               # AAZ Perfumes
│   ├── shoptime.py          # Shoptime
│   ├── kingofparfums.py     # The King of Parfums
│   └── beautybox.py         # Beautybox
├── database/
│   ├── models.py            # Modelos SQLAlchemy
│   ├── db.py                # Conexão e inicialização
│   └── repository.py        # Repositórios de dados
├── wordpress/
│   ├── client.py            # Cliente REST API WordPress
│   └── sync.py              # Serviço de sincronização
├── scheduler/
│   ├── scheduler.py         # Configuração APScheduler
│   └── tasks.py             # Tarefas agendadas
├── dashboard/
│   ├── app.py               # FastAPI + rotas web
│   └── templates/           # Templates HTML
├── data/                    # Banco de dados SQLite (criado automaticamente)
├── logs/                    # Logs de execução (criado automaticamente)
├── main.py                  # Ponto de entrada principal
├── setup.py                 # Script de configuração inicial
├── requirements.txt         # Dependências Python
├── .env.example             # Exemplo de configuração
└── README.md
```

## Instalação

### 1. Pré-requisitos

- Python 3.11+
- pip

### 2. Setup automático (recomendado)

```bash
python setup.py
```

### 3. Setup manual

```bash
# Instalar dependências
pip install -r requirements.txt

# Instalar browsers Playwright (opcional, para sites com JS)
playwright install chromium

# Criar arquivo de configuração
cp .env.example .env
# Edite o .env com suas configurações

# Inicializar banco de dados
python -c "from database.db import init_db; init_db()"
```

## Configuração

Edite o arquivo `.env`:

```env
# WordPress (opcional)
WP_URL=https://seu-site.com
WP_USERNAME=seu_usuario
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx

# Banco de dados
DB_PATH=./data/scentsearch.db

# Agendamento (padrão: 06:00 diariamente)
SCRAPE_HOUR=6
SCRAPE_MINUTE=0

# Painel web
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8000

# Configurações de scraping
REQUEST_DELAY=2
MAX_RETRIES=3
REQUEST_TIMEOUT=30
```

## Uso

### Iniciar o painel web (com agendador)

```bash
python main.py
```

Acesse: http://localhost:8000

### Executar scraping manualmente

```bash
# Todas as lojas
python -c "from scrapers.manager import ScrapingManager; ScrapingManager().run_all()"

# Loja específica
python -c "from scrapers.manager import ScrapingManager; ScrapingManager().run_store('amazon')"
```

### API REST

O painel expõe endpoints JSON:

- `GET /api/stats` — estatísticas gerais
- `GET /api/jobs` — jobs agendados
- `GET /api/stores` — lojas cadastradas

## Integração WordPress

1. No WordPress, vá em **Usuários → Seu Perfil**
2. Role até **Senhas de Aplicativos**
3. Crie uma senha com o nome `ScentSearch`
4. Configure no `.env`: `WP_USERNAME`, `WP_APP_PASSWORD`, `WP_URL`
5. No painel, acesse **WordPress** e clique em **Sincronizar**

## Adicionando um novo Scraper

```python
# scrapers/minhaloja.py
from scrapers.base import BaseScraper, ScrapingResult, PriceData

class MinhaLojaScraper(BaseScraper):
    store_name = "Minha Loja"
    store_slug = "minhaloja"
    base_url = "https://www.minhaloja.com.br"

    def scrape(self) -> ScrapingResult:
        soup = self.get_page(f"{self.base_url}/perfumes")
        for product in soup.select(".product"):
            name = product.select_one(".name").text
            price = self.parse_price(product.select_one(".price").text)
            url = product.select_one("a")["href"]
            self.result.products.append(PriceData(name=name, url=url, price=price))
        return self.result
```

Depois registre em `scrapers/manager.py`:
```python
from scrapers.minhaloja import MinhaLojaScraper
SCRAPER_REGISTRY["minhaloja"] = MinhaLojaScraper
```

## Extensibilidade

O sistema é projetado para ser reutilizado em outros comparadores:

- **Beleza**: Mude `category = "beleza"` na classe base
- **Pet**: Mude `category = "pet"` e crie novos scrapers
- **Qualquer nicho**: Herde `BaseScraper`, implemente `scrape()`

## Licença

MIT
