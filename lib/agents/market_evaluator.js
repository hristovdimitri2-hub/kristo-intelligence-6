/**
 * Market Demand & Auto-Evolution Agent
 * ====================================
 * Независим модул за сканиране на пазарното търсене на x402 микро-услуги.
 *
 * Функционалност:
 *   1. Сканира публични източници (CoinGecko трендове, DeFiLlama протоколи,
 *      GitHub trending x402 репозитории) за нови пазарни трендове.
 *   2. При откриване на нов тренд изпраща Telegram известие за одобрение
 *      с inline бутон (Approve / Reject).
 *   3. След одобрение от оператора, трендът се записва в локален state файл
 *      и може да бъде подаден към основния Kristo Intelligence агент.
 *
 * ВАЖНО: Този модул е НЕЗАВИСИМ и не променя базовата структура нито
 * съществуващите 8 агента на Kristo Intelligence. Той се стартира отделно
 * и комуникира само чрез Telegram + state файл.
 *
 * Използване:
 *   node lib/agents/market_evaluator.js
 *   node lib/agents/market_evaluator.js --once     # единичен цикъл
 *   node lib/agents/market_evaluator.js --loop     # непрекъснат режим
 *
 * Конфигурация (env променливи):
 *   TELEGRAM_BOT_TOKEN      - Telegram bot token за известия
 *   TELEGRAM_CHAT_ID        - Chat ID на оператора (получател на известията)
 *   MARKET_SCAN_INTERVAL    - Интервал между сканиранията в секунди (default 600)
 *   MARKET_STATE_FILE       - Път до state файл (default ./market_state.json)
 *   COINGECKO_API_KEY        - Опционален CoinGecko API key
 *
 * Лиценз: MIT
 */

'use strict';

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

// ── Конфигурация от environment ────────────────────────────────────────────
const CONFIG = {
  telegramToken: process.env.TELEGRAM_BOT_TOKEN || '',
  telegramChatId: process.env.TELEGRAM_CHAT_ID || '',
  scanInterval: parseInt(process.env.MARKET_SCAN_INTERVAL || '600', 10),
  stateFile: process.env.MARKET_STATE_FILE || path.join(process.cwd(), 'market_state.json'),
  coingeckoApiKey: process.env.COINGECKO_API_KEY || '',
  once: process.argv.includes('--once'),
  loop: process.argv.includes('--loop'),
};

const log = (level, msg, ...args) => {
  const ts = new Date().toISOString();
  const prefix = `[${ts}] [${level.toUpperCase()}] [MarketEvaluator]`;
  if (level === 'error') {
    console.error(prefix, msg, ...args);
  } else {
    console.log(prefix, msg, ...args);
  }
};

// ── State управление ────────────────────────────────────────────────────────
function loadState() {
  try {
    if (fs.existsSync(CONFIG.stateFile)) {
      return JSON.parse(fs.readFileSync(CONFIG.stateFile, 'utf8'));
    }
  } catch (e) {
    log('warn', 'State file parse failed, starting fresh:', e.message);
  }
  return {
    knownTrends: {},      // trendId -> {firstSeen, approved, metadata}
    pendingApprovals: {}, // callbackId -> {trendId, timestamp}
    scanCount: 0,
    lastScan: null,
  };
}

function saveState(state) {
  try {
    fs.writeFileSync(CONFIG.stateFile, JSON.stringify(state, null, 2), 'utf8');
  } catch (e) {
    log('error', 'Failed to save state:', e.message);
  }
}

// ── HTTP helper ────────────────────────────────────────────────────────────
function fetchJSON(url, options = {}) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.get(url, options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(new Error(`JSON parse error for ${url}: ${e.message}`));
          }
        } else {
          reject(new Error(`HTTP ${res.statusCode} for ${url}`));
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => {
      req.destroy();
      reject(new Error(`Request timeout for ${url}`));
    });
  });
}

// ── Telegram helper ────────────────────────────────────────────────────────
function telegramAPI(method, body) {
  return new Promise((resolve, reject) => {
    if (!CONFIG.telegramToken) {
      return reject(new Error('TELEGRAM_BOT_TOKEN not configured'));
    }
    const url = `https://api.telegram.org/bot${CONFIG.telegramToken}/${method}`;
    const payload = JSON.stringify(body);
    const req = https.request(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    }, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('Telegram API timeout'));
    });
    req.write(payload);
    req.end();
  });
}

/**
 * Изпраща Telegram известие за нов тренд с inline бутони за одобрение.
 * Връща callback_data ID, който се ползва за проследяване на одобрението.
 */
async function sendTrendApprovalNotification(trend) {
  if (!CONFIG.telegramToken || !CONFIG.telegramChatId) {
    log('warn', `Telegram not configured — trend ${trend.id} logged only:`, trend.title);
    return null;
  }

  const callbackId = `approve_${trend.id}`;
  const text = [
    `🔔 *Нов пазарен тренд открит!*`,
    ``,
    `*Име:* ${trend.title}`,
    `*Категория:* ${trend.category}`,
    `*Източник:* ${trend.source}`,
    `*Demand Score:* ${trend.demandScore}/100`,
    `*Тип:* ${trend.type}`,
    ``,
    `*Описание:*`,
    `${trend.description}`,
    ``,
    `💡 Предложена x402 микро-услуга: \`${trend.suggestedService}\``,
    ``,
    `✅ Approve — създай микро-услуга`,
    `❌ Reject — пропусни тренд`,
  ].join('\n');

  const inlineKeyboard = {
    inline_keyboard: [
      [
        { text: '✅ Approve', callback_data: callbackId },
        { text: '❌ Reject', callback_data: `reject_${trend.id}` },
      ],
    ],
  };

  try {
    const result = await telegramAPI('sendMessage', {
      chat_id: CONFIG.telegramChatId,
      text: text,
      parse_mode: 'Markdown',
      reply_markup: inlineKeyboard,
    });
    if (result.ok) {
      log('info', `Telegram approval notification sent for trend ${trend.id}`);
      return callbackId;
    } else {
      log('error', 'Telegram API error:', result.description);
      return null;
    }
  } catch (e) {
    log('error', 'Failed to send Telegram notification:', e.message);
    return null;
  }
}

// ── Trend detection: CoinGecko trending coins ──────────────────────────────
async function scanCoinGeckoTrending() {
  const trends = [];
  try {
    const url = 'https://api.coingecko.com/api/v3/search/trending';
    const data = await fetchJSON(url);
    if (data && Array.isArray(data.coins)) {
      for (const item of data.coins.slice(0, 5)) {
        const coin = item.item;
        trends.push({
          id: `cg_${coin.id}`,
          title: `${coin.name} (${coin.symbol})`,
          category: 'crypto_trending',
          source: 'CoinGecko Trending',
          demandScore: Math.min(100, (coin.market_cap_rank ? 100 - coin.market_cap_rank : 50) + 20),
          type: 'trending_token',
          description: `Токен ${coin.name} набира популярност в CoinGecko trending списъка. Rank: ${coin.market_cap_rank || 'N/A'}.`,
          suggestedService: `x402-price-feed-${coin.id}`,
          metadata: { coinId: coin.id, symbol: coin.symbol, rank: coin.market_cap_rank },
        });
      }
    }
  } catch (e) {
    log('warn', 'CoinGecko trending scan failed:', e.message);
  }
  return trends;
}

// ── Trend detection: DeFiLlama top protocols ───────────────────────────────
async function scanDeFiLlamaProtocols() {
  const trends = [];
  try {
    const url = 'https://api.llama.fi/protocols';
    const data = await fetchJSON(url);
    if (Array.isArray(data)) {
      // Топ 5 протокола по TVL растеж (сортирани по TVL)
      const top = data
        .filter((p) => p.tvl && p.tvl > 1000000)
        .sort((a, b) => b.tvl - a.tvl)
        .slice(0, 5);
      for (const proto of top) {
        trends.push({
          id: `dl_${proto.name.toLowerCase().replace(/\s+/g, '_')}`,
          title: `${proto.name} (${proto.chain || 'multi-chain'})`,
          category: 'defi_protocol',
          source: 'DeFiLlama',
          demandScore: Math.min(100, Math.round((proto.tvl / 100000000) * 10 + 30)),
          type: 'high_tvl_protocol',
          description: `DeFi протокол ${proto.name} с TVL $${(proto.tvl / 1e6).toFixed(1)}M на ${proto.chain || 'multi-chain'}.`,
          suggestedService: `x402-defi-monitor-${proto.name.toLowerCase().replace(/\s+/g, '-')}`,
          metadata: { name: proto.name, chain: proto.chain, tvl: proto.tvl },
        });
      }
    }
  } catch (e) {
    log('warn', 'DeFiLlama scan failed:', e.message);
  }
  return trends;
}

// ── Trend detection: x402 GitHub repos ─────────────────────────────────────
async function scanX402GitHubRepos() {
  const trends = [];
  try {
    const url = 'https://api.github.com/search/repositories?q=x402+micro-service&sort=stars&order=desc&per_page=5';
    const data = await fetchJSON(url, {
      headers: { 'User-Agent': 'Kristo-MarketEvaluator/1.0' },
    });
    if (data && Array.isArray(data.items)) {
      for (const repo of data.items) {
        trends.push({
          id: `gh_${repo.id}`,
          title: `${repo.full_name} ⭐${repo.stargazers_count}`,
          category: 'x402_microservice',
          source: 'GitHub Search',
          demandScore: Math.min(100, Math.round(repo.stargazers_count / 10) + 20),
          type: 'x402_repo',
          description: `GitHub репозитория ${repo.full_name} с ${repo.stargazers_count} stars. ${repo.description || ''}`,
          suggestedService: `x402-integration-${repo.name}`,
          metadata: { repoId: repo.id, stars: repo.stargazers_count, url: repo.html_url },
        });
      }
    }
  } catch (e) {
    log('warn', 'GitHub x402 scan failed:', e.message);
  }
  return trends;
}

// ── Farcaster / Warpcast Preview Bot (Growth & Incentive Engine) ───────────
/**
 * Генерира безплатни частични "тизър" сигнали за публикуване в социалните
 * мрежи за AI агенти (Farcaster/Warpcast). Тизърите съдържат само част от
 * сигнала и насочват към платената x402 версия за пълния анализ.
 *
 * Стратегия:
 *   - Всеки тизър съдържа заглавие, частичен сигнал (teaser) и CTA линк.
 *   - Пълният сигнал остава зад x402 paywall ($0.05 USDC, $0.01 при обем).
 *   - Тизърите се публикуват автоматично (ако FARCASTER_BOT_TOKEN е зададен)
 *     или само се логват (за ръчно публикуване).
 */

const FARCASTER_API_BASE = 'https://api.warpcast.com/v2';

/**
 * Генерира тизър текст за Farcast от пълен тренд/сигнал.
 * Тизърът съдържа само "hook" частта — без конкретни стойности.
 */
function generateFarcasterTeaser(trend) {
  const hookLines = [
    `🔥 ${trend.title} е в тренд!`,
    `📈 Засечен нов пазарен сигнал: ${trend.category}`,
    `⚡ ${trend.title} — demand score ${trend.demandScore}/100`,
  ];
  const hook = hookLines[Math.floor(Math.random() * hookLines.length)];

  // Частична информация (teaser) — без конкретни стойности/адреси
  const teaser = trend.description.length > 120
    ? trend.description.substring(0, 117) + '...'
    : trend.description;

  // CTA към платената x402 версия
  const cta = `→ Пълен сигнал + on-chain анализ: платена x402 версия ($0.05 USDC, $0.01 при обем)`;

  // Farcast формат (max 320 chars)
  const cast = `${hook}\n\n${teaser}\n\n${cta}\n\n#DeFi #Base #x402 #AI`;

  return cast.length > 320 ? cast.substring(0, 317) + '...' : cast;
}

/**
 * Публикува cast (тизър) във Farcaster/Warpcast чрез bot API.
 * Изисква FARCASTER_BOT_TOKEN в environment.
 */
async function publishFarcasterCast(text) {
  const token = process.env.FARCASTER_BOT_TOKEN || '';
  if (!token) {
    log('info', `[Farcaster] Bot token not set — teaser logged only:\n${text}`);
    return false;
  }

  return new Promise((resolve) => {
    const payload = JSON.stringify({ text });
    const req = https.request(`${FARCASTER_API_BASE}/casts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Content-Length': Buffer.byteLength(payload),
      },
    }, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          log('info', `[Farcaster] Cast published successfully.`);
          resolve(true);
        } else {
          log('warn', `[Farcaster] Publish failed: HTTP ${res.statusCode} — ${data}`);
          resolve(false);
        }
      });
    });
    req.on('error', (e) => {
      log('warn', `[Farcaster] Publish error: ${e.message}`);
      resolve(false);
    });
    req.setTimeout(15000, () => {
      req.destroy();
      log('warn', '[Farcaster] Publish timeout.');
      resolve(false);
    });
    req.write(payload);
    req.end();
  });
}

/**
 * Генерира и (опционално) публикува тизъри за всички нови трендове.
 * Връща масив от генерирани тизъри.
 */
async function generateAndPublishTeasers(trends, state) {
  const teasers = [];
  for (const trend of trends) {
    // Само за нови трендове, които още нямат публикуван тизър
    const trendState = state.knownTrends[trend.id];
    if (trendState && trendState.teaserPublished) continue;

    const teaserText = generateFarcasterTeaser(trend);
    teasers.push({ trendId: trend.id, text: teaserText });

    // Публикувай (или логвай ако няма token)
    await publishFarcasterCast(teaserText);

    // Маркирай че тизърът е публикуван
    if (state.knownTrends[trend.id]) {
      state.knownTrends[trend.id].teaserPublished = true;
      state.knownTrends[trend.id].teaserPublishedAt = new Date().toISOString();
    }
  }
  if (teasers.length > 0) {
    log('info', `[Farcaster] Generated ${teasers.length} teaser(s) for social publishing.`);
  }
  return teasers;
}

// ── Главен scan цикъл ───────────────────────────────────────────────────────
async function runScanCycle(state) {
  log('info', 'Starting market demand scan cycle...');
  state.scanCount++;
  state.lastScan = new Date().toISOString();

  // Паралелно сканиране на всички източници
  const [cgTrends, dlTrends, ghTrends] = await Promise.allSettled([
    scanCoinGeckoTrending(),
    scanDeFiLlamaProtocols(),
    scanX402GitHubRepos(),
  ]);

  const allTrends = [];
  if (cgTrends.status === 'fulfilled') allTrends.push(...cgTrends.value);
  if (dlTrends.status === 'fulfilled') allTrends.push(...dlTrends.value);
  if (ghTrends.status === 'fulfilled') allTrends.push(...ghTrends.value);

  log('info', `Scan complete: ${allTrends.length} trends found.`);

  let newTrendCount = 0;
  const newTrendsForTeaser = [];
  for (const trend of allTrends) {
    if (!state.knownTrends[trend.id]) {
      // Нов тренд — изпрати известие за одобрение
      log('info', `New trend detected: ${trend.id} — ${trend.title}`);
      state.knownTrends[trend.id] = {
        firstSeen: new Date().toISOString(),
        approved: null, // null = pending, true = approved, false = rejected
        metadata: trend.metadata,
        title: trend.title,
        category: trend.category,
        suggestedService: trend.suggestedService,
        teaserPublished: false,
      };

      const callbackId = await sendTrendApprovalNotification(trend);
      if (callbackId) {
        state.pendingApprovals[callbackId] = {
          trendId: trend.id,
          timestamp: new Date().toISOString(),
        };
      }
      newTrendCount++;
      newTrendsForTeaser.push(trend);
    }
  }

  // ── Farcaster/Warpcast: генерирай и публикувай тизъри за новите трендове ──
  if (newTrendsForTeaser.length > 0) {
    await generateAndPublishTeasers(newTrendsForTeaser, state);
  }

  log('info', `Cycle done: ${newTrendCount} new trends, ${allTrends.length} total.`);
  saveState(state);
  return { newTrendCount, totalTrends: allTrends.length };
}

// ── Polling за Telegram callback (одобрения) ───────────────────────────────
async function pollTelegramCallbacks(state) {
  if (!CONFIG.telegramToken) return;

  try {
    const offset = state._tgOffset || 0;
    const result = await telegramAPI('getUpdates', {
      offset: offset,
      limit: 10,
      timeout: 0,
      allowed_updates: ['callback_query'],
    });

    if (result.ok && Array.isArray(result.result)) {
      for (const update of result.result) {
        state._tgOffset = update.update_id + 1;
        if (update.callback_query) {
          const cb = update.callback_query;
          const data = cb.data || '';
          const chatId = cb.message && cb.message.chat && cb.message.chat.id;

          log('info', `Telegram callback received: ${data} from chat ${chatId}`);

          if (data.startsWith('approve_')) {
            const trendId = data.substring(8);
            if (state.knownTrends[trendId]) {
              state.knownTrends[trendId].approved = true;
              state.knownTrends[trendId].approvedAt = new Date().toISOString();
              log('info', `Trend ${trendId} APPROVED by operator.`);
              await telegramAPI('answerCallbackQuery', {
                callback_query_id: cb.id,
                text: `✅ Тренд ${trendId} одобрен! Микро-услуга ще бъде създадена.`,
              });
              await telegramAPI('sendMessage', {
                chat_id: chatId,
                text: `✅ *Одобрено!* Тренд \`${trendId}\` е одобрен.\nПредложена услуга: \`${state.knownTrends[trendId].suggestedService}\``,
                parse_mode: 'Markdown',
              });
            }
          } else if (data.startsWith('reject_')) {
            const trendId = data.substring(7);
            if (state.knownTrends[trendId]) {
              state.knownTrends[trendId].approved = false;
              state.knownTrends[trendId].rejectedAt = new Date().toISOString();
              log('info', `Trend ${trendId} REJECTED by operator.`);
              await telegramAPI('answerCallbackQuery', {
                callback_query_id: cb.id,
                text: `❌ Тренд ${trendId} отхвърлен.`,
              });
            }
          }
        }
      }
      saveState(state);
    }
  } catch (e) {
    log('warn', 'Telegram callback poll failed:', e.message);
  }
}

// ── Main ──────────────────────────────────────────────────────────────────
async function main() {
  log('info', '=== Market Demand & Auto-Evolution Agent ===');
  log('info', `Config: interval=${CONFIG.scanInterval}s, state=${CONFIG.stateFile}`);
  log('info', `Telegram: ${CONFIG.telegramToken ? 'configured' : 'NOT configured (log only)'}`);
  log('info', `Mode: ${CONFIG.once ? 'once' : CONFIG.loop ? 'loop' : 'once'}`);

  const state = loadState();

  if (CONFIG.once || !CONFIG.loop) {
    // Единичен цикъл
    await runScanCycle(state);
    await pollTelegramCallbacks(state);
    log('info', 'Single cycle complete. Exiting.');
    return;
  }

  // Непрекъснат режим
  log('info', 'Starting continuous loop mode. Press Ctrl+C to stop.');

  // Първоначален scan
  await runScanCycle(state);

  // Polling цикъл
  setInterval(async () => {
    try {
      await runScanCycle(state);
      await pollTelegramCallbacks(state);
    } catch (e) {
      log('error', 'Cycle error:', e.message);
    }
  }, CONFIG.scanInterval * 1000);

  // Poll Telegram callbacks по-често
  setInterval(async () => {
    try {
      await pollTelegramCallbacks(state);
    } catch (e) {
      log('warn', 'Callback poll error:', e.message);
    }
  }, 15000);
}

main().catch((e) => {
  log('error', 'Fatal error:', e.message);
  process.exit(1);
});