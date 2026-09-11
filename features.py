def extract_features_from_token_data(data: dict) -> dict:
    """
    Transforms raw DEX metrics and manipulation indicators into predictive quantitative signals.
    """
    buys_5m = data.get("buys_5m", 0)
    sells_5m = data.get("sells_5m", 0)
    total_tx_5m = buys_5m + sells_5m
    buy_ratio_5m = (buys_5m / total_tx_5m) if total_tx_5m > 0 else 0.5
    
    buys_1h = data.get("buys_1h", 0)
    sells_1h = data.get("sells_1h", 0)
    total_tx_1h = buys_1h + sells_1h
    buy_ratio_1h = (buys_1h / total_tx_1h) if total_tx_1h > 0 else 0.5

    # 1. Order Flow Imbalance (OFI) normalized between -1.0 (all sells) and +1.0 (all buys)
    ofi_5m = ((buys_5m - sells_5m) / total_tx_5m) if total_tx_5m > 0 else 0.0

    # 2. Volume Acceleration (Normalized 5m velocity vs 1h base)
    expected_5m_vol = data.get("volume_1h", 0.0) / 12.0
    vol_acceleration = (data.get("volume_5m", 0.0) / expected_5m_vol) if expected_5m_vol > 0 else 1.0
    
    # 3. Liquidity to FDV Ratio
    fdv = data.get("fdv", 0.0)
    liquidity_usd = data.get("liquidity_usd", 0.0)
    liq_to_fdv = (liquidity_usd / fdv) if fdv > 0 else 0.0

    # 4. Wash Trading Manipulation Score
    wash_analysis = data.get("wash_analysis", {})
    wash_score = wash_analysis.get("wash_score", 0.0)

    # 5. Microsoft Qlib Formulaic Alpha Factors
    pc_5m = float(data.get("price_change_5m", 0.0))
    pc_1h = float(data.get("price_change_1h", 0.0))

    # Alpha 1: Price-Volume Correlation (Qlib Alpha158 style)
    # Checks if volume expansion genuinely drives price expansion (+1.0) vs churn/distribution (-1.0)
    if vol_acceleration > 1.2:
        alpha_pv_corr = 1.0 if pc_5m > 0 else (-1.0 if pc_5m < 0 else 0.0)
    else:
        alpha_pv_corr = 0.2 if pc_5m > 0 else (-0.2 if pc_5m < 0 else 0.0)

    # Alpha 2: Momentum Velocity & Acceleration
    # Compares 5m surge against expected average 5m interval velocity over 1h
    expected_5m_rate = pc_1h / 12.0
    alpha_momentum_accel = pc_5m - expected_5m_rate

    # Alpha 3: Volatility Skew (normalized 5m impulse vs 1h net move)
    alpha_vol_skew = (abs(pc_5m) / (abs(pc_1h) + 1.0)) * (1.0 if pc_5m >= 0 else -1.0)

    return {
        "buy_ratio_5m": float(buy_ratio_5m),
        "buy_ratio_1h": float(buy_ratio_1h),
        "ofi_5m": float(ofi_5m),
        "vol_acceleration": float(min(vol_acceleration, 10.0)),
        "price_change_5m": float(pc_5m),
        "price_change_1h": float(pc_1h),
        "liq_to_fdv": float(liq_to_fdv),
        "liquidity_usd": float(liquidity_usd),
        "wash_score": float(wash_score),
        "alpha_pv_corr": float(alpha_pv_corr),
        "alpha_momentum_accel": float(alpha_momentum_accel),
        "alpha_vol_skew": float(alpha_vol_skew)
    }
