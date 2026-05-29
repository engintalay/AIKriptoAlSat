// ==========================================================================
// AI KRİPTO AL-SAT - FRONTEND SCRIPT (NATIVE ES6)
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
    // Bildirim izni iste (HTTPS'de çalışır)
    if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
    }

    // global State
    let selectedCoin = null;
    let selectedTimeframe = "1h";
    let allCoins = [];
    let favorites = [];
    let currentFilter = "all";
    
    // TradingView Grafik Nesneleri
    let chart = null;
    let candleSeries = null;
    let volumeSeries = null;
    let indicatorSeries = []; // Aktif indikatör serileri
    let activeIndicators = new Set();

    // DOM Elementleri
    const scannerTableBody = document.getElementById("scanner-table-body");
    const scannerSearch = document.getElementById("scanner-search");
    const filterTabs = document.querySelectorAll(".filter-tab");
    
    const workspaceEmpty = document.getElementById("no-selected-coin");
    const workspaceContent = document.getElementById("selected-coin-workspace");
    
    const detailCoinSymbol = document.getElementById("detail-coin-symbol");
    const detailCoinName = document.getElementById("detail-coin-name");
    const detailCoinPrice = document.getElementById("detail-coin-price");
    const detailCoinChange = document.getElementById("detail-coin-change");
    const detailRsiVal = document.getElementById("detail-rsi-val");
    const detailScoreVal = document.getElementById("detail-score-val");
    const rsiFill = document.querySelector(".rsi-fill");
    const scoreFill = document.querySelector(".score-fill");
    
    const technicalReasonsList = document.getElementById("technical-reasons-list");
    
    const chartContainer = document.getElementById("tradingview-chart-container");
    const chartLoader = document.getElementById("chart-loader");
    const reportLoader = document.getElementById("report-loader");
    const reportActualData = document.getElementById("report-actual-data");
    
    const reportDirection = document.getElementById("report-direction");
    const reportSummaryText = document.getElementById("report-summary-text");
    const reportEntry = document.getElementById("report-entry");
    const reportStop = document.getElementById("report-stop");
    const reportTp1 = document.getElementById("report-tp1");
    const reportTp2 = document.getElementById("report-tp2");
    const reportTechnical = document.getElementById("report-technical-analysis");
    const reportPatterns = document.getElementById("report-patterns");
    const reportLeverage = document.getElementById("report-leverage");
    const reportRisk = document.getElementById("report-risk-assessment");
    
    const chatMessages = document.getElementById("chat-messages");
    const chatInput = document.getElementById("chat-input");
    const btnSendMessage = document.getElementById("btn-send-message");
    const chatSuggestions = document.querySelectorAll(".btn-suggest");
    
    const backtestCardsContainer = document.getElementById("backtest-cards-container");
    
    // Butonlar
    const btnScanNow = document.getElementById("btn-scan-now");
    const scanIcon = document.getElementById("scan-icon");
    const btnOpenSettings = document.getElementById("btn-open-settings");
    const btnCloseSettings = document.getElementById("btn-close-settings");
    const settingsModal = document.getElementById("settings-modal");
    const btnSaveSettings = document.getElementById("btn-save-settings");
    const btnRefreshReport = document.getElementById("btn-refresh-report");
    const btnToggleFavDetail = document.getElementById("btn-toggle-favorite-detail");
    const detailFavIcon = document.getElementById("detail-fav-icon");

    // ==========================================================================
    // 1. TRADINGVIEW HAFİF GRAFİK (LIGHTWEIGHT CHARTS) BAŞLATMA
    // ==========================================================================
    function initChart() {
        if (chart) return; // Zaten oluşturulmuşsa es geç
        
        chartContainer.innerHTML = ""; // Temizle
        
        // Grafik Yapılandırması (Karanlık Glassmorphism Teması)
        chart = LightweightCharts.createChart(chartContainer, {
            layout: {
                background: { type: 'solid', color: '#0d0e15' },
                textColor: '#8a92b2',
                fontFamily: 'Outfit, sans-serif',
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.02)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.02)' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
                timeVisible: true,
                secondsVisible: false,
            },
            localization: {
                timeFormatter: (timestamp) => {
                    const date = new Date(timestamp * 1000);
                    return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
                },
                dateFormatter: (timestamp) => {
                    const date = new Date(timestamp * 1000);
                    return date.toLocaleDateString('tr-TR');
                },
            },
        });

        // 1. Mum Serisi Ekle
        candleSeries = chart.addCandlestickSeries({
            upColor: '#00e676',
            downColor: '#ff3d00',
            borderUpColor: '#00e676',
            borderDownColor: '#ff3d00',
            wickUpColor: '#00e676',
            wickDownColor: '#ff3d00',
            priceFormat: { type: 'price', precision: 4, minMove: 0.0001 },
        });

        // 2. Altına Hacim Serisi Ekle (Küçük ölçekli)
        volumeSeries = chart.addHistogramSeries({
            color: '#2979ff',
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // Ayrı dikey ölçek
        });
        
        // Hacim ölçeğini grafiğin en altında %20'lik alana yerleştir
        chart.priceScale('').applyOptions({
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });
        
        // Mum ölçeğini en üstte %75'lik alana sığdır
        chart.priceScale('right').applyOptions({
            scaleMargins: {
                top: 0.1,
                bottom: 0.25,
            },
        });

        // Pencere Boyutu Değiştiğinde Grafik Uyumunu Sağla
        window.addEventListener("resize", () => {
            if (chart) {
                chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
            }
        });
    }

    // ==========================================================================
    // 2. PİYASA TARAMA MOTORU VE LİSTELEME
    // ==========================================================================
    async function runMarketScan(force = false) {
        if (force) {
            scanIcon.classList.add("fa-spin");
            btnScanNow.disabled = true;
        }

        try {
            const res = await fetch(`/api/scan?force=${force}`);
            const data = await res.json();
            
            allCoins = data.coins || [];
            
            // Exchange badge güncelle
            const ex = (data.exchange || "binance").toUpperCase();
            document.getElementById("exchange-badge").textContent = ex;
            
            // İstatistik Kartlarını Güncelle
            document.getElementById("val-scanned-count").innerText = allCoins.length;
            const activeSigs = allCoins.filter(c => c.signal.includes("BUY") || c.signal.includes("SELL")).length;
            document.getElementById("val-active-signals").innerText = activeSigs;
            
            renderScannerTable();
            renderBacktestHistory();
            
            // Eğer ilk yükleme ise ve henüz coin seçilmemişse listedeki 1. coini seçelim
            if (!selectedCoin && allCoins.length > 0) {
                selectCoin(allCoins[0].symbol);
            }
        } catch (err) {
            console.error("Tarama hatası:", err);
            scannerTableBody.innerHTML = `<tr><td colspan="7" class="table-empty text-red"><i class="fa-solid fa-triangle-exclamation"></i> Veriler yüklenirken bağlantı hatası oluştu.</td></tr>`;
        } finally {
            if (force) {
                scanIcon.classList.remove("fa-spin");
                btnScanNow.disabled = false;
            }
        }
    }

    function renderScannerTable() {
        const query = scannerSearch.value.toLowerCase().trim();
        
        let filtered = allCoins.filter(c => c.symbol.toLowerCase().includes(query));
        
        // Tab Filtresi Uygula
        if (currentFilter === "favs") {
            filtered = filtered.filter(c => c.is_favorite);
        } else if (currentFilter === "bull") {
            filtered = filtered.filter(c => c.signal.includes("BUY"));
        } else if (currentFilter === "bear") {
            filtered = filtered.filter(c => c.signal.includes("SELL"));
        } else if (currentFilter === "oversold") {
            filtered = filtered.filter(c => c.rsi < 30 || c.rsi > 70);
        }

        if (filtered.length === 0) {
            scannerTableBody.innerHTML = `<tr><td colspan="8" class="table-empty">Eşleşen sonuç bulunamadı.</td></tr>`;
            return;
        }

        scannerTableBody.innerHTML = "";
        
        filtered.forEach(coin => {
            const tr = document.createElement("tr");
            tr.dataset.symbol = coin.symbol;
            if (selectedCoin === coin.symbol) {
                tr.classList.add("active");
            }

            // Son güncelleme zamanını formatla
            const lastUpdated = coin.updated_at ? new Date(coin.updated_at) : new Date();
            const timeDiff = Date.now() - lastUpdated.getTime();
            let updateTimeText = "Yeni";
            if (timeDiff > 60000) {
                const mins = Math.floor(timeDiff / 60000);
                updateTimeText = mins + " dk";
            }
            const updateTimeClass = timeDiff < 60000 ? "text-green" : (timeDiff < 300000 ? "text-gold" : "text-red");

            // Değişim Badgesi
            const isUp = coin.change_24h >= 0;
            const changeClass = isUp ? "up" : "down";
            const changeSign = isUp ? "+" : "";

            // Sinyal Sınıfı
            let sigClass = "hold";
            if (coin.signal === "STRONG BUY") sigClass = "strong-buy";
            else if (coin.signal === "BUY") sigClass = "buy";
            else if (coin.signal === "SELL") sigClass = "sell";
            else if (coin.signal === "STRONG SELL") sigClass = "strong-sell";

            // RSI Uyarısı
            let rsiClass = "";
            if (coin.rsi < 30) rsiClass = "oversold";
            else if (coin.rsi > 70) rsiClass = "overbought";

            // Skor Sınıfı
            let scoreClass = "mid";
            if (coin.ai_score >= 70) scoreClass = "high";
            else if (coin.ai_score < 40) scoreClass = "low";

            // Satır HTML
            tr.innerHTML = `
                <td>
                    <button class="star-btn ${coin.is_favorite ? 'fav' : ''}" data-symbol="${coin.symbol}">
                        <i class="${coin.is_favorite ? 'fa-solid' : 'fa-regular'} fa-star"></i>
                    </button>
                </td>
                <td>
                    <div class="coin-sym">
                        <span class="coin-sym-name">${coin.symbol.replace("USDT", "")}</span>
                        <span class="coin-sym-sub">USDT</span>
                    </div>
                </td>
                <td class="text-right price-text">$${formatPrice(coin.price)}</td>
                <td class="text-right">
                    <span class="change-pill ${changeClass}">${changeSign}${coin.change_24h.toFixed(2)}%</span>
                </td>
                <td class="text-right rsi-cell">
                    <span>${coin.rsi.toFixed(1)}</span>
                    <div class="rsi-bar-container">
                        <div class="rsi-bar-indicator ${rsiClass}" style="width: ${coin.rsi}%"></div>
                    </div>
                </td>
                <td class="text-center">
                    <span class="score-badge ${scoreClass}">${coin.ai_score}</span>
                </td>
                <td class="text-center">
                    <span class="sig-badge ${sigClass}">${coin.signal}</span>
                </td>
                <td class="text-right">
                    <span class="update-time ${updateTimeClass}">${updateTimeText}</span>
                </td>
            `;

            // Satır tıklama dinleyicisi (favori yıldızına basıldığında coin seçilmesin)
            tr.addEventListener("click", (e) => {
                if (e.target.closest(".star-btn")) return;
                selectCoin(coin.symbol);
            });

            scannerTableBody.appendChild(tr);
        });

        // Yıldız butonları dinleyicisi
        document.querySelectorAll(".star-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const sym = btn.dataset.symbol;
                await toggleFavoriteAPI(sym);
            });
        });
    }

    // ==========================================================================
    // 3. COIN SEÇİMİ VE VERİLERİNİ YÜKLEME
    // ==========================================================================
    function selectCoin(symbol) {
        selectedCoin = symbol;
        
        // Tabloda aktiflik durumunu güncelle
        document.querySelectorAll("#scanner-table-body tr").forEach(tr => {
            if (tr.dataset.symbol === symbol) tr.classList.add("active");
            else tr.classList.remove("active");
        });

        workspaceEmpty.classList.add("hidden");
        workspaceContent.classList.remove("hidden");

        // Coin detay bilgilerini bul
        const coin = allCoins.find(c => c.symbol === symbol);
        if (!coin) return;

        // Üst panel güncelleme
        detailCoinSymbol.innerText = coin.symbol.replace("USDT", " / USDT");
        detailCoinName.innerText = getCoinFullName(coin.symbol);
        detailCoinPrice.innerText = `$${formatPrice(coin.price)}`;
        
        const isUp = coin.change_24h >= 0;
        detailCoinChange.innerText = `${isUp ? '+' : ''}${coin.change_24h.toFixed(2)}%`;
        detailCoinChange.className = `change-badge ${isUp ? 'up' : 'down'}`;
        
        detailRsiVal.innerText = coin.rsi.toFixed(1);
        rsiFill.style.width = `${coin.rsi}%`;
        
        detailScoreVal.innerText = `${coin.ai_score}/100`;
        scoreFill.style.width = `${coin.ai_score}%`;
        
        // AI skor rengi ayarla
        if (coin.ai_score >= 70) detailScoreVal.className = "gauge-value text-green";
        else if (coin.ai_score < 40) detailScoreVal.className = "gauge-value text-red";
        else detailScoreVal.className = "gauge-value text-gold";

        // Favori Yıldız Butonunu Güncelle
        if (coin.is_favorite) {
            btnToggleFavDetail.classList.add("active");
            detailFavIcon.className = "fa-solid fa-star text-gold";
        } else {
            btnToggleFavDetail.classList.remove("active");
            detailFavIcon.className = "fa-regular fa-star";
        }

        // Teknik Bulguları Listele
        technicalReasonsList.innerHTML = "";
        const reasons = coin.details?.reasons || [];
        if (reasons.length === 0) {
            technicalReasonsList.innerHTML = `<li>Herhangi bir kritik indikatör kırılımı saptanmadı. Trend stabil.</li>`;
        } else {
            reasons.forEach(r => {
                const li = document.createElement("li");
                li.innerText = r;
                technicalReasonsList.appendChild(li);
            });
        }

        // Grafiği ve AI Raporu yükle
        initChart();
        loadChartData();
        loadAIReport();
        loadChatHistory();
    }

    // Coin yenile butonu
    document.getElementById("btn-refresh-coin").addEventListener("click", async function() {
        if (!selectedCoin) return;
        this.classList.add("spinning");
        try {
            const res = await fetch(`/api/coin/${selectedCoin}/refresh`);
            if (res.ok) {
                const updated = await res.json();
                // allCoins'deki veriyi güncelle
                const idx = allCoins.findIndex(c => c.symbol === selectedCoin);
                if (idx !== -1) { Object.assign(allCoins[idx], updated); }
                selectCoin(selectedCoin);
            }
        } catch(e) { console.error("Coin yenileme hatası:", e); }
        this.classList.remove("spinning");
    });

    // ==========================================================================
    // 4. TRADINGVIEW GRAFİĞİNE MUM VERİLERİNİ ÇİZME
    // ==========================================================================
    async function loadChartData() {
        if (!selectedCoin || !chart) return;
        
        chartLoader.classList.remove("hidden");
        
        try {
            const indParam = Array.from(activeIndicators).join(",");
            const bbPeriod = document.getElementById("ind-bb-period")?.value || 20;
            const bbStd = document.getElementById("ind-bb-std")?.value || 2;
            const stPeriod = document.getElementById("ind-st-period")?.value || 10;
            const stMult = document.getElementById("ind-st-mult")?.value || 3;
            const ichTenkan = document.getElementById("ind-ich-tenkan")?.value || 9;
            const ichKijun = document.getElementById("ind-ich-kijun")?.value || 26;
            const ichSenkou = document.getElementById("ind-ich-senkou")?.value || 52;
            const res = await fetch(`/api/coin/${selectedCoin}/candles?interval=${selectedTimeframe}&indicators=${indParam}&bb_period=${bbPeriod}&bb_std=${bbStd}&st_period=${stPeriod}&st_mult=${stMult}&ich_tenkan=${ichTenkan}&ich_kijun=${ichKijun}&ich_senkou=${ichSenkou}`);
            const data = await res.json();
            
            const candles = data.candles || data;
            const indicators = data.indicators || {};
            
            if (candles && candles.length > 0) {
                candleSeries.setData(candles);
                
                const volumes = candles.map(item => ({
                    time: item.time,
                    value: item.volume,
                    color: item.close >= item.open ? 'rgba(0, 230, 118, 0.3)' : 'rgba(255, 61, 0, 0.3)'
                }));
                volumeSeries.setData(volumes);
                
                // Eski indikatör serilerini kaldır
                indicatorSeries.forEach(s => { try { chart.removeSeries(s); } catch(e) {} });
                indicatorSeries = [];
                
                const times = candles.map(c => c.time);
                
                // Bollinger Bandı
                if (indicators.bb_upper) {
                    const bbUpper = chart.addLineSeries({ color: '#2979ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
                    const bbMid = chart.addLineSeries({ color: '#ffab00', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
                    const bbLower = chart.addLineSeries({ color: '#2979ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
                    bbUpper.setData(times.map((t, i) => indicators.bb_upper[i] != null ? {time: t, value: indicators.bb_upper[i]} : null).filter(Boolean));
                    bbMid.setData(times.map((t, i) => indicators.bb_mid[i] != null ? {time: t, value: indicators.bb_mid[i]} : null).filter(Boolean));
                    bbLower.setData(times.map((t, i) => indicators.bb_lower[i] != null ? {time: t, value: indicators.bb_lower[i]} : null).filter(Boolean));
                    indicatorSeries.push(bbUpper, bbMid, bbLower);
                }
                
                // SuperTrend
                if (indicators.supertrend) {
                    const stUp = chart.addLineSeries({ color: '#00e676', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
                    const stDown = chart.addLineSeries({ color: '#ff3d00', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
                    const upData = [], downData = [];
                    times.forEach((t, i) => {
                        if (indicators.supertrend[i] == null) return;
                        if (indicators.supertrend_dir[i] === 1) upData.push({time: t, value: indicators.supertrend[i]});
                        else downData.push({time: t, value: indicators.supertrend[i]});
                    });
                    stUp.setData(upData);
                    stDown.setData(downData);
                    indicatorSeries.push(stUp, stDown);
                }
                
                // Ichimoku
                if (indicators.ichimoku_tenkan) {
                    const tenkan = chart.addLineSeries({ color: '#2979ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
                    const kijun = chart.addLineSeries({ color: '#ff3d00', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
                    const senkouA = chart.addLineSeries({ color: 'rgba(0,230,118,0.5)', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
                    const senkouB = chart.addLineSeries({ color: 'rgba(255,61,0,0.5)', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
                    tenkan.setData(times.map((t, i) => indicators.ichimoku_tenkan[i] != null ? {time: t, value: indicators.ichimoku_tenkan[i]} : null).filter(Boolean));
                    kijun.setData(times.map((t, i) => indicators.ichimoku_kijun[i] != null ? {time: t, value: indicators.ichimoku_kijun[i]} : null).filter(Boolean));
                    senkouA.setData(times.map((t, i) => indicators.ichimoku_senkou_a[i] != null ? {time: t, value: indicators.ichimoku_senkou_a[i]} : null).filter(Boolean));
                    senkouB.setData(times.map((t, i) => indicators.ichimoku_senkou_b[i] != null ? {time: t, value: indicators.ichimoku_senkou_b[i]} : null).filter(Boolean));
                    indicatorSeries.push(tenkan, kijun, senkouA, senkouB);
                }
                
                chart.timeScale().fitContent();
            }
        } catch (err) {
            console.error("Grafik mum yükleme hatası:", err);
        } finally {
            chartLoader.classList.add("hidden");
        }
    }

    // ==========================================================================
    // 5. AI AL-SAT STRATEJİ RAPORU
    // ==========================================================================
    let reportAbortController = null;
    const btnStopReport = document.getElementById("btn-stop-report");

    async function loadAIReport(forceRefresh = false) {
        if (!selectedCoin) return;
        
        // Önceki isteği iptal et
        if (reportAbortController) reportAbortController.abort();
        reportAbortController = new AbortController();
        
        reportLoader.classList.remove("hidden");
        reportActualData.classList.add("hidden");
        btnStopReport.classList.remove("hidden");
        
        // Stream preview göster
        reportLoader.innerHTML = '<div class="report-stream-preview" id="report-stream-preview"><span class="stream-label">AI üretiyor...</span><pre id="report-stream-text" data-think-started="" data-stream-started=""></pre></div>';
        
        try {
            const url = `/api/coin/${selectedCoin}/report${forceRefresh ? '?refresh=true' : ''}`;
            const res = await fetch(url, { signal: reportAbortController.signal });
            const report = await res.json();
            console.log("[DEBUG] AI Rapor:", report);
            
            // Strateji Kartını Doldur
            reportDirection.innerText = report.direction;
            
            // Sinyal Yönü Tasarımı
            if (report.direction.includes("BUY") || report.direction.includes("LONG")) {
                reportDirection.className = "direction-pill long";
            } else if (report.direction.includes("SELL") || report.direction.includes("SHORT")) {
                reportDirection.className = "direction-pill short";
            } else {
                reportDirection.className = "direction-pill hold";
            }

            reportSummaryText.innerText = report.summary;
            reportEntry.innerText = report.entry_zone;
            reportStop.innerText = report.stop_loss;
            reportTp1.innerText = report.take_profit_1;
            reportTp2.innerText = report.take_profit_2;
            
            reportTechnical.innerText = report.technical_analysis;
            reportPatterns.innerText = report.chart_patterns;
            reportLeverage.innerText = report.leverage_advice;
            reportRisk.innerText = report.risk_assessment;
            
            reportActualData.classList.remove("hidden");
        } catch (err) {
            if (err.name === 'AbortError') {
                console.log("AI Rapor isteği durduruldu.");
            } else {
                console.error("AI Rapor yükleme hatası:", err);
            }
        } finally {
            reportLoader.classList.add("hidden");
            btnStopReport.classList.add("hidden");
            reportAbortController = null;
        }
    }

    btnStopReport.addEventListener("click", () => {
        if (reportAbortController) reportAbortController.abort();
        fetch("/api/ai/abort", { method: "POST" });
    });

    // ==========================================================================
    // 6. COIN AI CHAT (SOHBET ASİSTANI)
    // ==========================================================================
    async function loadChatHistory() {
        if (!selectedCoin) return;
        
        chatMessages.innerHTML = "";
        
        // Varsayılan Hoş Geldiniz Mesajı
        const welcomeDiv = document.createElement("div");
        welcomeDiv.className = "chat-bubble ai";
        welcomeDiv.innerText = `Merhaba! Ben ${selectedCoin.replace("USDT", "")} AI Asistanıyım. Mum grafiği, formasyonlar, destek/direnç seviyeleri, kaldıraç veya zarar kes noktası hakkında sorularını yanıtlamaya hazırım.`;
        chatMessages.appendChild(welcomeDiv);
        
        try {
            const res = await fetch(`/api/coin/${selectedCoin}/chat`);
            const history = await res.json();
            
            history.forEach(msg => {
                const bubble = document.createElement("div");
                bubble.className = `chat-bubble ${msg.sender.toLowerCase()}`;
                bubble.innerHTML = formatMarkdown(msg.message);
                chatMessages.appendChild(bubble);
            });
            
            scrollToBottomChat();
        } catch (err) {
            console.error("Chat geçmişi yükleme hatası:", err);
        }
    }

    async function sendUserMessage(msgText) {
        if (!msgText || !selectedCoin) return;
        
        // Kullanıcı mesaj balonunu çiz
        const userBubble = document.createElement("div");
        userBubble.className = "chat-bubble user";
        userBubble.innerText = msgText;
        chatMessages.appendChild(userBubble);
        scrollToBottomChat();
        
        // Inputu temizle
        chatInput.value = "";
        
        // Yazıyor... Balonunu Ekle
        const loaderBubble = document.createElement("div");
        loaderBubble.className = "chat-bubble ai loader";
        loaderBubble.id = "chat-typing-loader";
        loaderBubble.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Düşünüyor...`;
        chatMessages.appendChild(loaderBubble);
        scrollToBottomChat();

        try {
            const res = await fetch(`/api/coin/${selectedCoin}/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: msgText })
            });
            const data = await res.json();
            
            // Yazıyor balonunu kaldır
            const typingLdr = document.getElementById("chat-typing-loader");
            if (typingLdr) typingLdr.remove();
            
            // AI Mesajını çiz
            const aiBubble = document.createElement("div");
            aiBubble.className = "chat-bubble ai";
            aiBubble.innerHTML = formatMarkdown(data.reply);
            chatMessages.appendChild(aiBubble);
            
            scrollToBottomChat();
        } catch (err) {
            console.error("Mesaj gönderilemedi:", err);
            const typingLdr = document.getElementById("chat-typing-loader");
            if (typingLdr) typingLdr.remove();
            
            const errBubble = document.createElement("div");
            errBubble.className = "chat-bubble ai text-red";
            errBubble.innerText = "Yapay zeka asistanına şu an erişilemiyor. Lütfen API anahtarınızı veya bağlantınızı kontrol edin.";
            chatMessages.appendChild(errBubble);
            scrollToBottomChat();
        }
    }

    // ==========================================================================
    // 7. BACKTEST VE GEÇMİŞ SİNYAL TAKİBİ
    // ==========================================================================
    async function renderBacktestHistory() {
        try {
            const res = await fetch("/api/signals");
            const signals = await res.json();
            
            if (!signals || signals.length === 0) {
                backtestCardsContainer.innerHTML = `<div class="backtest-empty">Henüz tetiklenen Al-Sat sinyali bulunmamaktadır. Tarama devam ediyor...</div>`;
                return;
            }
            
            // Başarı Oranını ve Toplam P&L Hesapla
            const closedSigs = signals.filter(s => s.status !== "PENDING");
            const pendingSigs = signals.filter(s => s.status === "PENDING").length;
            const wins = closedSigs.filter(s => s.status.includes("TP")).length;
            const losses = closedSigs.filter(s => s.status === "SL_HIT").length;
            const totalPnl = closedSigs.reduce((sum, s) => sum + (s.pnl || 0), 0);
            
            if (closedSigs.length > 0) {
                const winRate = (wins / closedSigs.length) * 100;
                const pnlStr = totalPnl >= 0 ? `+$${totalPnl.toFixed(0)}` : `-$${Math.abs(totalPnl).toFixed(0)}`;
                const pnlColor = totalPnl >= 0 ? "text-green" : "text-red";
                document.getElementById("val-win-rate").innerHTML = `${winRate.toFixed(0)}% (${wins}W/${losses}L) <span class="${pnlColor}">${pnlStr}</span>`;
            } else {
                document.getElementById("val-win-rate").innerText = `${pendingSigs} beklemede`;
            }
            
            backtestCardsContainer.innerHTML = "";
            
            signals.forEach(sig => {
                const card = document.createElement("div");
                card.className = `sig-card ${sig.status}`;
                
                let statusText = "⏳ BEKLEMEDE";
                if (sig.status === "TP1_HIT") statusText = "🎯 TP1";
                else if (sig.status === "TP2_HIT") statusText = "🚀 TP2";
                else if (sig.status === "SL_HIT") statusText = "🛑 STOP";
                
                const pnlClass = sig.pnl >= 0 ? "pnl-positive" : "pnl-negative";
                const pnlText = sig.status === "PENDING" ? "" : `<span class="${pnlClass}">${sig.pnl >= 0 ? '+' : ''}$${sig.pnl.toFixed(1)} (${sig.pnl_pct >= 0 ? '+' : ''}${sig.pnl_pct}%)</span>`;
                const closedText = sig.closed_price ? `→ $${formatPrice(sig.closed_price)}` : "";
                
                card.innerHTML = `
                    <div class="sig-card-header">
                        <span class="sig-card-sym">${sig.symbol.replace("USDT", "")}</span>
                        <span class="sig-card-type ${sig.type.toLowerCase()}">${sig.type === "BUY" ? "LONG" : "SHORT"}</span>
                    </div>
                    <div class="sig-card-prices">
                        <span>$${formatPrice(sig.entry_price)} ${closedText}</span>
                    </div>
                    <div class="sig-card-status">
                        <span>${statusText}</span>
                        ${pnlText}
                    </div>
                `;
                
                card.addEventListener("click", () => selectCoin(sig.symbol));
                backtestCardsContainer.appendChild(card);
            });
        } catch (err) {
            console.error("Backtest geçmişi yükleme hatası:", err);
        }
    }

    // ==========================================================================
    // 8. FAVORİ APİ VE AYARLAR YÖNETİMİ
    // ==========================================================================
    async function toggleFavoriteAPI(symbol) {
        try {
            const res = await fetch(`/api/coin/${symbol}/favorite`, { method: "POST" });
            const data = await res.json();
            
            // Yerel state'i güncelle
            const coin = allCoins.find(c => c.symbol === symbol);
            if (coin) {
                coin.is_favorite = data.is_favorite;
            }
            
            // Eğer seçili coin buysa yıldız durumunu güncelle
            if (selectedCoin === symbol) {
                if (data.is_favorite) {
                    btnToggleFavDetail.classList.add("active");
                    detailFavIcon.className = "fa-solid fa-star text-gold";
                } else {
                    btnToggleFavDetail.classList.remove("active");
                    detailFavIcon.className = "fa-regular fa-star";
                }
            }
            
            renderScannerTable();
        } catch (err) {
            console.error("Favori güncelleme hatası:", err);
        }
    }

    async function loadSettings() {
        try {
            const res = await fetch("/api/settings");
            const settings = await res.json();
            
            document.getElementById("input-gemini-key").value = settings.gemini_api_key_configured ? "••••••••••••••••••••••••" : "";
            document.getElementById("input-coins-limit").value = settings.top_coins_limit;
            document.getElementById("input-scan-interval").value = settings.scan_interval_minutes;
            document.getElementById("input-backtest-amount").value = settings.backtest_amount || 1000;
            
            const provider = settings.llm_provider || "gemini";
            const exchange = settings.exchange || "binance";
            
            document.getElementById("select-llm-provider").value = provider;
            document.getElementById("select-exchange").value = exchange;
            document.getElementById("input-ollama-model").value = settings.ollama_model || "llama3";
            document.getElementById("input-ollama-url").value = settings.ollama_api_url || "http://localhost:11434";
            document.getElementById("input-llamacpp-url").value = settings.llamacpp_api_url || "http://localhost:8080";
            document.getElementById("input-kucoin-rate-limit").value = settings.kucoin_rate_limit || 60;
            
            // Dinamik görünüm durumunu güncelle
            const geminiGrp = document.getElementById("settings-group-gemini");
            const ollamaGrp = document.getElementById("settings-group-ollama");
            const llamacppGrp = document.getElementById("settings-group-llamacpp");
            const kucoinGrp = document.getElementById("settings-group-kucoin");
            
            geminiGrp.classList.add("hidden");
            ollamaGrp.classList.add("hidden");
            llamacppGrp.classList.add("hidden");
            kucoinGrp.classList.add("hidden");
            
            if (provider === "ollama") {
                ollamaGrp.classList.remove("hidden");
            } else if (provider === "llamacpp") {
                llamacppGrp.classList.remove("hidden");
            } else {
                geminiGrp.classList.remove("hidden");
            }
            
            if (exchange === "kucoin") {
                kucoinGrp.classList.remove("hidden");
            }
        } catch (err) {
            console.error("Ayarlar yüklenemedi:", err);
        }
    }

    async function saveSettingsAPI() {
        const provider = document.getElementById("select-llm-provider").value;
        const exchange = document.getElementById("select-exchange").value;
        const geminiKey = document.getElementById("input-gemini-key").value;
        const limit = parseInt(document.getElementById("input-coins-limit").value) || 50;
        const interval = parseInt(document.getElementById("input-scan-interval").value) || 15;
        const ollamaModel = document.getElementById("input-ollama-model").value.trim() || "llama3";
        const ollamaUrl = document.getElementById("input-ollama-url").value.trim() || "http://localhost:11434";
        const llamacppUrl = document.getElementById("input-llamacpp-url").value.trim() || "http://localhost:8080";
        const kucoinKey = document.getElementById("input-kucoin-key").value;
        const kucoinSecret = document.getElementById("input-kucoin-secret").value;
        const kucoinPassphrase = document.getElementById("input-kucoin-passphrase").value;
        const kucoinRateLimit = parseInt(document.getElementById("input-kucoin-rate-limit").value) || 60;
        
        const alertMsg = document.getElementById("settings-status-msg");
        
        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    gemini_api_key: geminiKey.includes("•••") ? "" : geminiKey,
                    top_coins_limit: limit,
                    scan_interval_minutes: interval,
                    backtest_amount: parseFloat(document.getElementById("input-backtest-amount").value) || 1000,
                    llm_provider: provider,
                    ollama_model: ollamaModel,
                    ollama_api_url: ollamaUrl,
                    llamacpp_api_url: llamacppUrl,
                    exchange: exchange,
                    kucoin_api_key: kucoinKey.includes("•••") ? "" : kucoinKey,
                    kucoin_api_secret: kucoinSecret.includes("•••") ? "" : kucoinSecret,
                    kucoin_api_passphrase: kucoinPassphrase.includes("•••") ? "" : kucoinPassphrase,
                    kucoin_rate_limit: kucoinRateLimit
                })
            });
            const data = await res.json();
            
            if (data.status === "success") {
                alertMsg.innerText = "Ayarlar başarıyla kaydedildi! Piyasa yeniden taranıyor...";
                alertMsg.className = "settings-status-alert success";
                alertMsg.classList.remove("hidden");
                
                setTimeout(() => {
                    alertMsg.classList.add("hidden");
                    settingsModal.classList.add("hidden");
                    runMarketScan(true);
                }, 2000);
            }
        } catch (err) {
            console.error("Ayarlar kaydedilirken hata:", err);
            alertMsg.innerText = "Kaydedilemedi. Bağlantınızı kontrol edin.";
            alertMsg.className = "settings-status-alert text-red";
            alertMsg.classList.remove("hidden");
        }
    }

    // ==========================================================================
    // 9. DİNLEYİCİLER (EVENT LISTENERS) VE YARDIMCILAR
    // ==========================================================================
    
    // Arama Çubuğu Dinleyicisi
    scannerSearch.addEventListener("input", () => {
        renderScannerTable();
    });

    // Filtre Tabları Dinleyicisi
    filterTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            filterTabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            currentFilter = tab.dataset.filter;
            renderScannerTable();
        });
    });

    // Zaman Dilimi Butonları Dinleyicisi
    document.querySelectorAll(".btn-timeframe").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".btn-timeframe").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            selectedTimeframe = btn.dataset.tf;
            loadChartData();
        });
    });

    // İndikatör toggle butonları
    document.querySelectorAll(".btn-indicator").forEach(btn => {
        btn.addEventListener("click", () => {
            const ind = btn.dataset.ind;
            btn.classList.toggle("active");
            if (activeIndicators.has(ind)) activeIndicators.delete(ind);
            else activeIndicators.add(ind);
            loadChartData();
        });
    });

    // İndikatör ayarları paneli
    const indSettingsPanel = document.getElementById("indicator-settings-panel");
    document.getElementById("btn-ind-settings").addEventListener("click", () => {
        indSettingsPanel.classList.toggle("hidden");
    });
    document.getElementById("btn-ind-apply").addEventListener("click", () => {
        indSettingsPanel.classList.add("hidden");
        loadChartData();
    });

    // Chat gizle/göster
    const chatCol = document.getElementById("chat-col");
    const btnShowChat = document.getElementById("btn-show-chat");
    const workspaceGrid = document.querySelector(".workspace-grid");
    document.getElementById("btn-hide-chat").addEventListener("click", () => {
        chatCol.style.display = "none";
        btnShowChat.style.display = "";
        workspaceGrid.style.gridTemplateColumns = "1fr 400px";
    });
    btnShowChat.addEventListener("click", () => {
        chatCol.style.display = "";
        btnShowChat.style.display = "none";
        workspaceGrid.style.gridTemplateColumns = "";
    });

    // Canlı Tara Butonu
    btnScanNow.addEventListener("click", () => {
        runMarketScan(true);
    });

    // Reset Signals butonu
    document.getElementById("btn-reset-signals").addEventListener("click", async () => {
        if (confirm("Tüm sinyal geçmişi silinecek. Emin misiniz?")) {
            await fetch("/api/signals/reset", { method: "POST" });
            renderBacktestHistory();
        }
    });

    // Sinyal görünüm toggle (kart/tablo)
    const cardsContainer = document.getElementById("backtest-cards-container");
    const tableContainer = document.getElementById("backtest-table-container");
    const btnViewCards = document.getElementById("btn-signals-view-cards");
    const btnViewTable = document.getElementById("btn-signals-view-table");
    
    btnViewCards.addEventListener("click", () => {
        cardsContainer.classList.remove("hidden");
        tableContainer.classList.add("hidden");
        btnViewCards.classList.add("active");
        btnViewTable.classList.remove("active");
    });
    btnViewTable.addEventListener("click", () => {
        cardsContainer.classList.add("hidden");
        tableContainer.classList.remove("hidden");
        btnViewTable.classList.add("active");
        btnViewCards.classList.remove("active");
        renderSignalsTable();
    });
    document.getElementById("btn-signals-expand").addEventListener("click", function() {
        const footer = document.querySelector(".app-footer-backtest");
        footer.classList.toggle("expanded");
        this.querySelector("i").className = footer.classList.contains("expanded") ? "fa-solid fa-compress" : "fa-solid fa-expand";
    });

    async function renderSignalsTable() {
        const res = await fetch("/api/signals");
        const signals = await res.json();
        const tbody = document.getElementById("signals-table-body");
        if (!signals || signals.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--text-secondary)">Sinyal yok</td></tr>`;
            return;
        }
        tbody.innerHTML = signals.map(sig => {
            const pnlClass = sig.pnl >= 0 ? "pnl-positive" : "pnl-negative";
            const pnlText = sig.status === "PENDING" ? "-" : `${sig.pnl >= 0 ? '+' : ''}$${sig.pnl.toFixed(1)} (${sig.pnl_pct}%)`;
            const statusMap = { "PENDING": "⏳", "TP1_HIT": "🎯 TP1", "TP2_HIT": "🚀 TP2", "SL_HIT": "🛑 SL" };
            const fmtDate = (d) => d ? new Date(d).toLocaleString("tr-TR", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}) : "-";
            return `<tr>
                <td><b>${sig.symbol.replace("USDT","")}</b></td>
                <td class="${sig.type === 'BUY' ? 'pnl-positive' : 'pnl-negative'}">${sig.type === "BUY" ? "LONG" : "SHORT"}</td>
                <td>$${formatPrice(sig.entry_price)}</td>
                <td>${sig.closed_price ? '$' + formatPrice(sig.closed_price) : '-'}</td>
                <td>$${formatPrice(sig.stop_loss)}</td>
                <td>$${formatPrice(sig.take_profit_1)}</td>
                <td>$${formatPrice(sig.take_profit_2)}</td>
                <td>${statusMap[sig.status] || sig.status}</td>
                <td class="${pnlClass}">${pnlText}</td>
                <td>${fmtDate(sig.created_at)}</td>
                <td>${fmtDate(sig.closed_at)}</td>
            </tr>`;
        }).join("");
    }

    // İndikatör Popup
    const indPopup = document.getElementById("indicators-popup");
    const indPopupContent = document.getElementById("indicators-popup-content");
    document.getElementById("btn-show-indicators").addEventListener("click", () => {
        if (indPopup.classList.contains("hidden")) {
            const coin = allCoins.find(c => c.symbol === selectedCoin);
            if (!coin || !coin.details) return;
            const d = typeof coin.details === "string" ? JSON.parse(coin.details) : coin.details;
            const rows = [
                ["RSI (14)", d.rsi?.toFixed(1) || "-", d.rsi > 70 ? "negative" : d.rsi < 30 ? "positive" : ""],
                ["MACD", d.macd?.toFixed(6) || "-", d.macd > d.macd_signal ? "positive" : "negative"],
                ["MACD Signal", d.macd_signal?.toFixed(6) || "-", ""],
                ["EMA 50", d.ema_50?.toFixed(4) || "-", coin.price > d.ema_50 ? "positive" : "negative"],
                ["EMA 200", d.ema_200?.toFixed(4) || "-", coin.price > d.ema_200 ? "positive" : "negative"],
                ["Bollinger Üst", d.bb_upper?.toFixed(4) || "-", ""],
                ["Bollinger Alt", d.bb_lower?.toFixed(4) || "-", ""],
                ["ATR", d.atr?.toFixed(4) || "-", ""],
                ["ATR %", (d.atr_pct?.toFixed(2) || "-") + "%", d.atr_pct > 5 ? "negative" : "positive"],
                ["BTC Dominance", (d.btc_dominance?.toFixed(1) || "-") + "%", d.btc_dominance > 55 ? "negative" : d.btc_dominance < 45 ? "positive" : ""],
            ];
            indPopupContent.innerHTML = rows.map(([label, val, cls]) =>
                `<div class="ind-row"><span class="ind-label">${label}</span><span class="ind-value ${cls}">${val}</span></div>`
            ).join("");
            // Reasons
            if (d.reasons && d.reasons.length) {
                indPopupContent.innerHTML += `<div style="margin-top:8px;font-size:11px;color:var(--text-secondary)"><b>Bulgular:</b><br>• ${d.reasons.join("<br>• ")}</div>`;
            }
        }
        indPopup.classList.toggle("hidden");
    });
    document.getElementById("btn-close-indicators").addEventListener("click", () => indPopup.classList.add("hidden"));

    // Rapor Yenile Butonu
    btnRefreshReport.addEventListener("click", () => {
        loadAIReport(true);
    });

    // Detay Favori Yıldız Butonu
    btnToggleFavDetail.addEventListener("click", () => {
        if (selectedCoin) {
            toggleFavoriteAPI(selectedCoin);
        }
    });

    // Ayarlar Pop-up Aç/Kapat
    btnOpenSettings.addEventListener("click", () => {
        loadSettings();
        settingsModal.classList.remove("hidden");
    });
    
    btnCloseSettings.addEventListener("click", () => {
        settingsModal.classList.add("hidden");
    });
    
    btnSaveSettings.addEventListener("click", () => {
        saveSettingsAPI();
    });
    
    // Şifre Görünürlüğü
    document.getElementById("btn-toggle-key-visibility").addEventListener("click", () => {
        const inp = document.getElementById("input-gemini-key");
        const icon = document.querySelector("#btn-toggle-key-visibility i");
        if (inp.type === "password") {
            inp.type = "text";
            icon.className = "fa-solid fa-eye-slash";
        } else {
            inp.type = "password";
            icon.className = "fa-solid fa-eye";
        }
    });

    // Yapay Zeka Sağlayıcısı Değişimi
    document.getElementById("select-llm-provider").addEventListener("change", (e) => {
        const val = e.target.value;
        const geminiGrp = document.getElementById("settings-group-gemini");
        const ollamaGrp = document.getElementById("settings-group-ollama");
        const llamacppGrp = document.getElementById("settings-group-llamacpp");
        
        geminiGrp.classList.add("hidden");
        ollamaGrp.classList.add("hidden");
        llamacppGrp.classList.add("hidden");
        
        if (val === "ollama") {
            ollamaGrp.classList.remove("hidden");
        } else if (val === "llamacpp") {
            llamacppGrp.classList.remove("hidden");
        } else {
            geminiGrp.classList.remove("hidden");
        }
    });

    // Borsa Seçimi Değişimi
    document.getElementById("select-exchange").addEventListener("change", (e) => {
        const val = e.target.value;
        const kucoinGrp = document.getElementById("settings-group-kucoin");
        
        if (val === "kucoin") {
            kucoinGrp.classList.remove("hidden");
        } else {
            kucoinGrp.classList.add("hidden");
        }
    });

    // KuCoin Şifre Görünürlüğü
    document.getElementById("btn-toggle-kucoin-key-visibility").addEventListener("click", () => {
        const inp = document.getElementById("input-kucoin-key");
        const icon = document.querySelector("#btn-toggle-kucoin-key-visibility i");
        if (inp.type === "password") {
            inp.type = "text";
            icon.className = "fa-solid fa-eye-slash";
        } else {
            inp.type = "password";
            icon.className = "fa-solid fa-eye";
        }
    });
    
    document.getElementById("btn-toggle-kucoin-secret-visibility").addEventListener("click", () => {
        const inp = document.getElementById("input-kucoin-secret");
        const icon = document.querySelector("#btn-toggle-kucoin-secret-visibility i");
        if (inp.type === "password") {
            inp.type = "text";
            icon.className = "fa-solid fa-eye-slash";
        } else {
            inp.type = "password";
            icon.className = "fa-solid fa-eye";
        }
    });
    
    document.getElementById("btn-toggle-kucoin-passphrase-visibility").addEventListener("click", () => {
        const inp = document.getElementById("input-kucoin-passphrase");
        const icon = document.querySelector("#btn-toggle-kucoin-passphrase-visibility i");
        if (inp.type === "password") {
            inp.type = "text";
            icon.className = "fa-solid fa-eye-slash";
        } else {
            inp.type = "password";
            icon.className = "fa-solid fa-eye";
        }
    });

    // Chat Gönderme Dinleyicileri
    btnSendMessage.addEventListener("click", () => {
        const text = chatInput.value.trim();
        if (text) sendUserMessage(text);
    });

    chatInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            const text = chatInput.value.trim();
            if (text) sendUserMessage(text);
        }
    });

    // Öneri butonları
    chatSuggestions.forEach(btn => {
        btn.addEventListener("click", () => {
            const text = btn.innerText;
            sendUserMessage(text);
        });
    });

    // Yardımcı Fonksiyonlar
    function formatPrice(p) {
        if (p >= 1000) return p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (p >= 1) return p.toFixed(2);
        if (p >= 0.01) return p.toFixed(4);
        return p.toFixed(6);
    }

    function scrollToBottomChat() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function getCoinFullName(symbol) {
        const names = {
            "BTCUSDT": "Bitcoin",
            "ETHUSDT": "Ethereum",
            "BNBUSDT": "BNB",
            "SOLUSDT": "Solana",
            "XRPUSDT": "Ripple",
            "ADAUSDT": "Cardano",
            "DOGEUSDT": "Dogecoin",
            "AVAXUSDT": "Avalanche",
            "DOTUSDT": "Polkadot",
            "LINKUSDT": "Chainlink",
            "MATICUSDT": "Polygon",
            "SHIBUSDT": "Shiba Inu",
            "LTCUSDT": "Litecoin",
            "NEARUSDT": "NEAR Protocol"
        };
        return names[symbol] || symbol.replace("USDT", "");
    }

    function formatMarkdown(text) {
        // En basit Markdown dönüşümü (**bold** ve yıldız işaretleri için liste formatı)
        let formatted = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>');
        return formatted;
    }

    // ==========================================================================
    // 10. UYGULAMAYI BAŞLAT
    // ==========================================================================
    runMarketScan(false); // İlk tarama, önbelleği getirecektir
    
    // Her 15 saniyede bir fiyatları/sinyal listesini arkada sessizce güncelle (Arayüz akıcılığı için)
    setInterval(() => {
        runMarketScan(false);
    }, 15 * 60 * 1000); // 15 dakika

    // ==========================================================================
    // AI LOG PANELİ
    // ==========================================================================
    const logPanel = document.getElementById("ai-log-panel");
    const logContent = document.getElementById("ai-log-content");
    const btnToggleLog = document.getElementById("btn-toggle-log");
    const btnCloseLog = document.getElementById("btn-close-log");
    const btnClearLog = document.getElementById("btn-clear-log");

    btnToggleLog.addEventListener("click", () => logPanel.classList.toggle("hidden"));
    btnCloseLog.addEventListener("click", () => logPanel.classList.add("hidden"));
    btnClearLog.addEventListener("click", () => { logContent.innerHTML = ""; });

    // SSE bağlantısı
    const logSource = new EventSource("/api/ai/logs");
    logSource.onmessage = (e) => {
        const line = e.data;
        let cls = "";
        if (line.includes("[SEND]")) cls = "log-send";
        else if (line.includes("[PROMPT]")) cls = "log-prompt";
        else if (line.includes("[STREAM]")) cls = "log-stream";
        else if (line.includes("[RECV]")) cls = "log-recv";
        else if (line.includes("[ABORT]")) cls = "log-abort";
        else if (line.includes("[INFO]")) cls = "log-info";
        else if (line.includes("[THINK]")) cls = "log-think";
        else if (line.includes("[SCAN]")) cls = "log-info";
        const div = document.createElement("div");
        div.className = cls;
        div.textContent = line;
        logContent.appendChild(div);
        logContent.scrollTop = logContent.scrollHeight;
        
        // Arka plan taraması bittiğinde ekranı güncelle ve bildirim at
        if (line.includes("[SCAN]")) {
            runMarketScan(false);
            renderBacktestHistory();
            // Web Notification (HTTPS gerektirir)
            if (Notification.permission === "granted") {
                const msg = line.split("[SCAN] ")[1] || "Yeni tarama tamamlandı";
                new Notification("AI Kripto Tarayıcı", { body: msg, icon: "/static/favicon.ico" });
            }
        }
        const div = document.createElement("div");
        div.className = cls;
        div.textContent = line;
        logContent.appendChild(div);
        logContent.scrollTop = logContent.scrollHeight;
        
        // Think verilerini de göster
        if (line.includes("[THINK]")) {
            const streamText = document.getElementById("report-stream-text");
            if (streamText) {
                const content = line.split("[THINK] ")[1] || "";
                // İlk think satırında başlık ekle
                if (!streamText.dataset.thinkStarted) {
                    streamText.textContent += "\n💭 Düşünüyor: ";
                    streamText.dataset.thinkStarted = "1";
                }
                streamText.textContent += content;
                streamText.scrollTop = streamText.scrollHeight;
            }
        }
        // Stream (asıl yanıt) verilerini rapor preview'a yaz
        if (line.includes("[STREAM]")) {
            const streamText = document.getElementById("report-stream-text");
            if (streamText) {
                // Think bittiyse ayraç ekle
                if (streamText.dataset.thinkStarted && !streamText.dataset.streamStarted) {
                    streamText.textContent += "\n\n═══ AI YANITI ═══\n";
                    streamText.dataset.streamStarted = "1";
                }
                const content = line.split("[STREAM] ")[1] || "";
                streamText.textContent += content;
                streamText.scrollTop = streamText.scrollHeight;
            }
        }
        // Prompt'u da göster
        if (line.includes("[PROMPT]")) {
            const streamText = document.getElementById("report-stream-text");
            if (streamText) {
                const content = line.split("[PROMPT] ")[1] || "";
                streamText.textContent += "\n📤 Prompt gönderildi (" + content.length + " karakter)\n";
            }
        }
        // Teknik verileri göster
        if (line.includes("[INFO]")) {
            const streamText = document.getElementById("report-stream-text");
            if (streamText) {
                const content = line.split("[INFO] ")[1] || "";
                streamText.textContent += content + "\n";
                streamText.scrollTop = streamText.scrollHeight;
            }
        }
    };
});
