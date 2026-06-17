# Benchmark de databases não convencionais em uma base de dados em grafo (OLTP)

O dataset [Twitch Gamers Social Network](https://snap.stanford.edu/data/twitch_gamers.html) é composto por nós que representam perfis na plataforma de streaming Twitch e arestas que implicam que os canais conectados seguem um ao outro. Isto posto, qual sistema de gerenciamento de banco de dados (SGBD) será mais eficiente em processar esses dados?
Para determinar a resposta dessa questão empregaremos quatro SGBDs: PostgreSQL, Neo4J, Cassandra e MongoDB. A nossa hipótese é que o Neo4J, por ser um database de grafos, será mais veloz e mais capaz que os outros.

## Ambiente experimental

Todos os SGBDs foram executados em containeres docker, conforme especificado no arquivo docker-compose.yml. Toda interação com os SGBDs será feita através da linguagem de programação Python. O computador no qual o experimento será executado possui as seguintes características:

- Sistema operacional: Windows 11 25H2
- Processador: Intel Core Ultra 7 265KF (3.90 GHz)
- RAM: A-DATA Technology AL2V56WCSV1-B1DS 2x16 DDR5
- Disco: NVMe SM2P41D3 ADATA 1024GB

## Observações

Temos como possíveis variáveis de confusão as consultas específicas utilizadas. Não necessariamente as consultas utilizadas aqui são a melhor maneira possível de obter os dados desejados dos SGBDs alvo. Ademais, computadores com outros conjuntos de hardware/software talvez obtenham resultados diferentes. Ademais, a virtualização docker pode interfirir nos resultados.

## Ingestão de dados

O dataset foi inserido nos bancos usando os scripts na pasta ingestion.

## Consultas

Organizamos uma lista de consultas para realizar em cada banco:

- Retornar uma conta.
- Retornar todos os afiliados de língua inglesa.
- Retornar views médias por língua.
- Retornar top 10 contas por views.
- Retornar todos os vizinhos diretos.
- Retornar todos os vizinhos de segundo grau
- Retornar o menor caminho indireto entre dois usuários.
- Retornar o menor caminho entre dois usuários

Rodamos as consultas dez vezes em cada banco de dados, descartando a primeira por causa do cache vazio.
Então medimos o tempo médio de cada consulta e seu desvio-padrão.

## Resultados

Por consulta:
Banco de dados (Tempo médio +/- desvio-padrão) (em ms)
1. Retornar uma conta:
    1. PostgreSQL (0.33 +/- 0.13)
    2. MongoDB (0.63 +/- 0.06)
    3. Neo4J (1.95 +/- 0.18)
    4. ScyllaDB (15.5 +/- 0.54)
2. Retornar todos os afiliados da língua inglesa:
    1. MongoDB (0.57 +/- 0.02)
    2. PostgreSQL (5.68 +/- 0.17)
    3. Neo4J (19.21 +/- 0.61)
    4. ScyllaDB (403.52 +/- 17.4)
3. Retornar views médias por língua:
    1. PostgreSQL (7.78 +/- 0.16)
    2. Neo4J (40.93 +/- 6.11)
    3. MongoDB (65.85 +/- 1.75)
    4. ScyllaDB (incapaz por conta própria)
4. Retornar top 10 contas por views:
    1. MongoDB (0.62 +/- 0.09)
    2. PostgreSQL (6.7 +/- 0.19)
    3. Neo4J (18.46 +/- 1.77)
    4. ScyllaDB (incapaz sem índices secundários)
5. Retornar todos os vizinhos diretos:
    1. MongoDB (0.55 +/- 0.03)
    2. Neo4J (1.99 +/- 0.14)
    3. ScyllaDB (15.65 +/- 0.4)
    4. PostgreSQL (79.23 +/- 2.42)
6. Retornar todos os vizinhos de segundo grau:
    1. PostgreSQL (506.01 +/- 13.89)
    2. Neo4J (710.52 +/- 10.69)
    3. ScyllaDB e MongoDB (não foram capazes)
7. Retornar o menor caminho indireto entre dois usuários:
    1. PostgreSQL (0.4 +/- 0.4)
    2. Neo4J (1.93 +/- 0.39)
    3. MongoDB (851.86 +/- 10.8)
    4. ScyllaDB (não foi capaz)
8. Retornar o menor caminho entre dois usuários:
    1. Neo4J (1.89 +/- 0.25)

# Benchmark de bancos de dados OLAP em uma base de dados de corridas de táxi

O dataset [TLC Yellow Taxi Trip Records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) é composto por registros de corridas de táxi amarelo na cidade de Nova York, contendo informações como localização de embarque e desembarque, distância percorrida, valores tarifários, gorjetas, taxas e forma de pagamento. Diante disso, qual sistema de gerenciamento de banco de dados OLAP será mais eficiente em processar consultas analíticas sobre esses dados?
Para isso foi realizado a comparação entre três bancos de dados, são eles: DuckDB, ClickHouse e ElasticSearch.

## Observações

A virtualização Docker pode interferir nos resultados do ClickHouse e do ElasticSearch, enquanto o DuckDB, por rodar diretamente no host, não sofre esse overhead. Por fim, o tamanho e a distribuição dos dados dentro de cada arquivo Parquet pode influenciar o comportamento do otimizador de cada banco.

## Ingestão de dados

O dataset foi inserido nos bancos usando os scripts na pasta `ingestion/`. Os dados utilizados correspondem ao mês de abril de 2026 do dataset Yellow Taxi Trip Records, totalizando 3.831.240 registros. A ingestão foi realizada a partir de arquivos no formato Parquet e inseridos em cada banco por meio de seus respectivos clientes Python.

## Consultas

Organizamos quatro consultas analíticas representativas de cenários reais de análise de transporte urbano:

- **PEAK_DEMAND:** Identificar os horários de pico de demanda, agrupando o volume de viagens por hora e dia da semana.
- **AIRPORT_DYNAMICS:** Analisar o comportamento de corridas com origem ou destino em aeroportos (JFK e LaGuardia), comparando tarifa média, distância e gorjeta em relação às demais corridas.
- **TIPPING_BEHAVIOR:** Entender o comportamento das gorjetas em pagamentos no cartão, relacionando o valor médio e percentual à quantidade de passageiros.
- **ROUTE_PROFITABILITY:** Descobrir as três rotas mais lucrativas por milha rodada para cada zona de origem, baseando-se na receita líquida de trajetos com alta frequência.

Rodamos cada consulta dez vezes em cada banco de dados, medindo o tempo médio de cada consulta e seu desvio-padrão nas 10 execuções.

## Resultados

Por consulta:
Banco de dados (Tempo médio +/- desvio-padrão) (em ms)

1. **PEAK_DEMAND:**
    1. DuckDB (6.15 +/- 0.28)
    2. ClickHouse (56.83 +/- 6.35)
    3. ElasticSearch (422.11 +/- 6.6)

2. **AIRPORT_DYNAMICS:**
    1. DuckDB (3.47 +/- 1.19)
    2. ElasticSearch (10.78 +/- 2.54)
    3. ClickHouse (51.31 +/- 1.19)

3. **TIPPING_BEHAVIOR:**
    1. DuckDB (5.58 +/- 0.31)
    2. ClickHouse (56.89 +/- 7.13)
    3. ElasticSearch (62 +/- 2.6)

4. **ROUTE_PROFITABILITY:**
    1. DuckDB (28.72 +/- 0.79)
    2. ClickHouse (52.01 +/- 8.95)
    3. ElasticSearch (930.33 +/- 27.73)
