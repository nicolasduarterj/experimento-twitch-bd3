# Benchmark de databases não convencionais em uma base de dados em grafo

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

## Consultas

## Resultados