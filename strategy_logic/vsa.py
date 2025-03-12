def detect_vsa_signals(df):
    """
    Анализирует объем и спред свечей для выявления сигналов VSA.
    """
    df['spread'] = df['high'] - df['low']
    df['volume_change'] = df['volume'].pct_change()

    df['vsa_signal'] = ""

    for i in range(1, len(df)):
        if df.loc[i, 'volume'] > df.loc[i - 1, 'volume'] * 1.5:
            if df.loc[i, 'spread'] < df.loc[i - 1, 'spread'] * 0.7:
                df.at[i, 'vsa_signal'] = "No Demand (Weakness)"
            elif df.loc[i, 'close'] > df.loc[i, 'open']:
                df.at[i, 'vsa_signal'] = "Accumulation (Strength)"
        elif df.loc[i, 'volume'] < df.loc[i - 1, 'volume'] * 0.7:
            if df.loc[i, 'spread'] > df.loc[i - 1, 'spread'] * 1.3:
                df.at[i, 'vsa_signal'] = "Supply Overcoming Demand (Weakness)"

    return df
