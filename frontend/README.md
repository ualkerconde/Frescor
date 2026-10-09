# Frontend — App de Contagem de Estoque (PWA)

App móvel em React + Vite, configurado como PWA (Progressive Web App).
Consome a API FastAPI construída no projeto `backend`.

## Pré-requisitos

- Node.js 18 ou superior instalado
- A API do backend rodando (ver pasta `backend`)

## Instalação e execução

```bash
# Instalar dependências
npm install

# Rodar em modo desenvolvimento (hot reload)
npm run dev
```

Acesse em `https://localhost:3000`.

> **Testes no celular (Android e iPhone)**: o servidor de desenvolvimento
> roda em **HTTPS** (certificado autoassinado), pois os celulares só
> liberam a câmera (leitor de código de barras) em conexão segura.
>
> 1. Rode o backend normalmente (`uvicorn app.main:app --reload`) — não
>    precisa de `--host 0.0.0.0`, pois o Vite encaminha as chamadas à API
>    pelo caminho `/backend` (ver `proxy` em `vite.config.js`).
> 2. Rode `npm run dev` e abra no celular o endereço "Network" que aparece
>    no terminal (ex: `https://192.168.0.65:3000`).
> 3. O navegador vai avisar que a conexão não é privada (o certificado é
>    autoassinado). Aceite uma vez:
>    - **Android (Chrome):** "Avançado" → "Continuar para ... (não seguro)"
>    - **iPhone (Safari):** "Mostrar Detalhes" → "visitar este site"
> 4. Ao abrir o scanner, o navegador pede a permissão da câmera.
>
> Como o IP do PC pode mudar, não é preciso editar nada: basta usar o novo
> endereço mostrado pelo `npm run dev`.

## Estrutura de pastas

```text
src/
├── App.jsx                  # Componente raiz, orquestra as telas
├── main.jsx                 # Ponto de entrada do React
├── index.css                # Estilos globais (reset, fontes)
├── components/
│   ├── ProdutoItem.jsx        # Linha de produto na lista de contagem
│   ├── SyncBanner.jsx         # Banner de status de sincronização
│   ├── BarcodeScanner.jsx     # Leitura de código de barras pela câmera (ZXing)
│   ├── Drawer.jsx             # Menu lateral (logout)
│   └── FiltroClassificacao.jsx # Filtro em cascata pelos níveis de classificação
├── hooks/
│   ├── useSync.js             # Lógica de sincronização automática (debounce)
│   └── useIsDesktop.js        # Detecta acesso via desktop (para bloqueio)
├── pages/
│   ├── LoginScreen.jsx      # Tela de login
│   ├── MainScreen.jsx       # Tela principal de contagem
│   └── DesktopBlockScreen.jsx # Tela de bloqueio para desktop
└── services/
    ├── api.js               # Comunicação com a API (fetch + refresh de token)
    └── storage.js            # Armazenamento local (cache + pendentes offline)
```

## Variáveis de ambiente

Copie `.env.example` para `.env` e ajuste:

```text
VITE_API_URL=http://127.0.0.1:8000   # URL da API em desenvolvimento
```

Em produção, use a URL do servidor com HTTPS:

```text
VITE_API_URL=https://api.seudominio.com.br
```

## Build para produção

```bash
npm run build
```

Gera a pasta `dist/` com todos os arquivos otimizados. Faça o deploy
dessa pasta em qualquer servidor web estático (Nginx, Netlify, Vercel, etc.).

## Funcionalidades implementadas

- Login com e-mail e senha (conectado à API real)
- Sessão persistente (Refresh Token de 30 dias)
- Lista de produtos com busca em tempo real (por nome, código interno, código de barras ou classificação)
- Leitura de código de barras pela câmera (scanner com ZXing)
- Filtro por níveis de classificação em cascata
- Campo numérico de contagem diretamente em cada produto
- Campo de peso informado (KG) para produtos sem peso médio cadastrado
- Salva automaticamente ao sair do campo (sem botão de confirmar)
- Indicador visual verde quando produto foi contado
- Indicador visual âmbar quando há contagem pendente de sincronização
- Sincronização automática 1.5s após qualquer alteração
- Funcionamento offline: salva no localStorage, sincroniza ao voltar online
- Estatísticas: total de produtos, contados, pendentes de sincronização
- Menu lateral (Drawer) com opção de logout
- Bloqueio de acesso via desktop
- Refresh automático de token (transparente para o usuário)

## Próximas funcionalidades (não implementadas ainda)

- Página de onboarding/instalação via QR Code
- Ícones reais do app (hoje usa placeholder)
