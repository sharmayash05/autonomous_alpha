"""
Technical Indicators
The Autonomous Alpha - TA Library Wrapper

This module provides technical indicator calculations:
- Trend indicators (EMA, SMA, MACD)
- Momentum indicators (RSI, Stochastic)
- Volatility indicators (ATR, Bollinger Bands)
- Volume indicators (OBV, VWAP)
"""

import numpy as np
from dataclasses import dataclass
from typing import Sequence


@dataclass
class MACD:
    """MACD indicator result"""
    macd_line: float
    signal_line: float
    histogram: float


@dataclass
class BollingerBands:
    """Bollinger Bands result"""
    upper: float
    middle: float
    lower: float
    bandwidth: float


@dataclass
class Stochastic:
    """Stochastic oscillator result"""
    k: float
    d: float


def sma(data: Sequence[float], period: int) -> list[float]:
    """Simple Moving Average"""
    result = []
    for i in range(len(data)):
        if i < period - 1:
            result.append(np.nan)
        else:
            result.append(np.mean(data[i - period + 1:i + 1]))
    return result


def ema(data: Sequence[float], period: int) -> list[float]:
    """Exponential Moving Average"""
    result = []
    multiplier = 2 / (period + 1)
    
    # First EMA is SMA
    first_sma = np.mean(data[:period])
    
    for i in range(len(data)):
        if i < period - 1:
            result.append(np.nan)
        elif i == period - 1:
            result.append(first_sma)
        else:
            prev_ema = result[-1]
            current_ema = (data[i] * multiplier) + (prev_ema * (1 - multiplier))
            result.append(current_ema)
            
    return result


def rsi(data: Sequence[float], period: int = 14) -> list[float]:
    """Relative Strength Index"""
    result = []
    gains = []
    losses = []
    
    for i in range(len(data)):
        if i == 0:
            result.append(np.nan)
            continue
            
        change = data[i] - data[i - 1]
        gain = change if change > 0 else 0
        loss = -change if change < 0 else 0
        
        gains.append(gain)
        losses.append(loss)
        
        if i < period:
            result.append(np.nan)
        elif i == period:
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            if avg_loss == 0:
                result.append(100)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - (100 / (1 + rs)))
        else:
            # Use smoothed averages
            prev_result = result[-1]
            if np.isnan(prev_result):
                result.append(np.nan)
                continue
                
            avg_gain = (gains[-2] * (period - 1) + gain) / period if len(gains) > 1 else gain
            avg_loss = (losses[-2] * (period - 1) + loss) / period if len(losses) > 1 else loss
            
            if avg_loss == 0:
                result.append(100)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - (100 / (1 + rs)))
                
    return result


def macd(
    data: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> list[MACD]:
    """Moving Average Convergence Divergence"""
    fast_ema = ema(data, fast_period)
    slow_ema = ema(data, slow_period)
    
    macd_line = [
        f - s if not (np.isnan(f) or np.isnan(s)) else np.nan
        for f, s in zip(fast_ema, slow_ema)
    ]
    
    # Filter NaN for signal calculation
    valid_macd = [m for m in macd_line if not np.isnan(m)]
    signal_ema = ema(valid_macd, signal_period) if valid_macd else []
    
    result = []
    signal_idx = 0
    
    for m in macd_line:
        if np.isnan(m):
            result.append(MACD(np.nan, np.nan, np.nan))
        elif signal_idx < len(signal_ema):
            s = signal_ema[signal_idx]
            h = m - s if not np.isnan(s) else np.nan
            result.append(MACD(m, s, h))
            signal_idx += 1
        else:
            result.append(MACD(m, np.nan, np.nan))
            
    return result


def atr(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    period: int = 14,
) -> list[float]:
    """Average True Range"""
    tr_values = []
    
    for i in range(len(high)):
        if i == 0:
            tr = high[i] - low[i]
        else:
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )
        tr_values.append(tr)
        
    return ema(tr_values, period)


def bollinger_bands(
    data: Sequence[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> list[BollingerBands]:
    """Bollinger Bands"""
    middle = sma(data, period)
    result = []
    
    for i in range(len(data)):
        if i < period - 1:
            result.append(BollingerBands(np.nan, np.nan, np.nan, np.nan))
        else:
            std = np.std(data[i - period + 1:i + 1])
            m = middle[i]
            upper = m + (std * std_dev)
            lower = m - (std * std_dev)
            bandwidth = (upper - lower) / m if m > 0 else 0
            result.append(BollingerBands(upper, m, lower, bandwidth))
            
    return result


def stochastic(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    k_period: int = 14,
    d_period: int = 3,
) -> list[Stochastic]:
    """Stochastic Oscillator"""
    k_values = []
    
    for i in range(len(close)):
        if i < k_period - 1:
            k_values.append(np.nan)
        else:
            highest_high = max(high[i - k_period + 1:i + 1])
            lowest_low = min(low[i - k_period + 1:i + 1])
            
            if highest_high == lowest_low:
                k_values.append(50)
            else:
                k = 100 * (close[i] - lowest_low) / (highest_high - lowest_low)
                k_values.append(k)
                
    d_values = sma(k_values, d_period)
    
    return [
        Stochastic(k, d)
        for k, d in zip(k_values, d_values)
    ]


def vwap(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float],
) -> list[float]:
    """Volume Weighted Average Price"""
    result = []
    cumulative_pv = 0
    cumulative_volume = 0
    
    for i in range(len(close)):
        typical_price = (high[i] + low[i] + close[i]) / 3
        pv = typical_price * volume[i]
        
        cumulative_pv += pv
        cumulative_volume += volume[i]
        
        if cumulative_volume > 0:
            result.append(cumulative_pv / cumulative_volume)
        else:
            result.append(np.nan)
            
    return result


def obv(
    close: Sequence[float],
    volume: Sequence[float],
) -> list[float]:
    """On-Balance Volume"""
    result = [0]
    
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            result.append(result[-1] + volume[i])
        elif close[i] < close[i - 1]:
            result.append(result[-1] - volume[i])
        else:
            result.append(result[-1])
            
    return result


def cmf(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float],
    period: int = 20,
) -> list[float]:
    """
    Chaikin Money Flow (CMF)
    Measures buying/selling pressure over a period.
    
    Positive values indicate accumulation (buying pressure)
    Negative values indicate distribution (selling pressure)
    
    Returns values typically between -1 and +1
    """
    result = []
    
    for i in range(len(close)):
        if i < period - 1:
            result.append(np.nan)
            continue
        
        # Calculate Money Flow Multiplier and Money Flow Volume for each period
        mf_volume_sum = 0
        volume_sum = 0
        
        for j in range(i - period + 1, i + 1):
            # Money Flow Multiplier = ((Close - Low) - (High - Close)) / (High - Low)
            hl_diff = high[j] - low[j]
            if hl_diff == 0:
                mf_multiplier = 0
            else:
                mf_multiplier = ((close[j] - low[j]) - (high[j] - close[j])) / hl_diff
            
            # Money Flow Volume = MF Multiplier * Volume
            mf_volume = mf_multiplier * volume[j]
            
            mf_volume_sum += mf_volume
            volume_sum += volume[j]
        
        # CMF = Sum(MF Volume) / Sum(Volume)
        if volume_sum == 0:
            result.append(0)
        else:
            result.append(mf_volume_sum / volume_sum)
    
    return result



def pivot_points(
    high: float,
    low: float,
    close: float,
) -> dict[str, float]:
    """Calculate pivot points from previous day"""
    pivot = (high + low + close) / 3
    
    return {
        "pivot": pivot,
        "r1": (2 * pivot) - low,
        "r2": pivot + (high - low),
        "r3": high + 2 * (pivot - low),
        "s1": (2 * pivot) - high,
        "s2": pivot - (high - low),
        "s3": low - 2 * (high - pivot),
    }


class TechnicalAnalyzer:
    """
    Convenience class for calculating multiple indicators on price data.
    """
    
    def __init__(
        self,
        prices: list[float],
        high: list[float] | None = None,
        low: list[float] | None = None,
        volume: list[float] | None = None,
    ):
        self.prices = prices
        self.high = high or prices
        self.low = low or prices
        self.volume = volume or [1.0] * len(prices)
        
    def get_all(self) -> dict:
        """Calculate all indicators"""
        return {
            "ema_20": ema(self.prices, 20)[-1] if len(self.prices) >= 20 else None,
            "ema_50": ema(self.prices, 50)[-1] if len(self.prices) >= 50 else None,
            "rsi_7": rsi(self.prices, 7)[-1] if len(self.prices) >= 8 else None,
            "rsi_14": rsi(self.prices, 14)[-1] if len(self.prices) >= 15 else None,
            "macd": macd(self.prices)[-1] if len(self.prices) >= 26 else None,
            "atr_14": atr(self.high, self.low, self.prices, 14)[-1] if len(self.prices) >= 15 else None,
            "bollinger": bollinger_bands(self.prices, 20)[-1] if len(self.prices) >= 20 else None,
            "stochastic": stochastic(self.high, self.low, self.prices)[-1] if len(self.prices) >= 17 else None,
            "vwap": vwap(self.high, self.low, self.prices, self.volume)[-1] if self.volume else None,
            "obv": obv(self.prices, self.volume)[-1] if self.volume and len(self.prices) >= 2 else None,
            "cmf": cmf(self.high, self.low, self.prices, self.volume, 20)[-1] if self.volume and len(self.prices) >= 20 else None,
        }
        
    def get_signal(self) -> str:
        """Get simple signal based on indicators"""
        indicators = self.get_all()
        
        score = 0
        
        # RSI signals
        rsi_val = indicators.get("rsi_14")
        if rsi_val:
            if rsi_val < 30:
                score += 2  # Oversold
            elif rsi_val < 40:
                score += 1
            elif rsi_val > 70:
                score -= 2  # Overbought
            elif rsi_val > 60:
                score -= 1
                
        # MACD signals
        macd_val = indicators.get("macd")
        if macd_val and not np.isnan(macd_val.histogram):
            if macd_val.histogram > 0:
                score += 1
            else:
                score -= 1
                
        # EMA trend
        ema_20 = indicators.get("ema_20")
        ema_50 = indicators.get("ema_50")
        current_price = self.prices[-1]
        
        if ema_20 and ema_50:
            if current_price > ema_20 and ema_20 > ema_50:
                score += 2  # Strong uptrend
            elif current_price > ema_20:
                score += 1
            elif current_price < ema_20 and ema_20 < ema_50:
                score -= 2  # Strong downtrend
            elif current_price < ema_20:
                score -= 1
                
        if score >= 3:
            return "STRONG_LONG"
        elif score >= 1:
            return "WEAK_LONG"
        elif score <= -3:
            return "STRONG_SHORT"
        elif score <= -1:
            return "WEAK_SHORT"
        else:
            return "NEUTRAL"


if __name__ == "__main__":
    # Test indicators
    import random
    
    # Generate sample data
    prices = [100]
    for _ in range(100):
        change = random.uniform(-2, 2)
        prices.append(prices[-1] + change)
        
    analyzer = TechnicalAnalyzer(prices)
    print("Indicators:", analyzer.get_all())
    print("Signal:", analyzer.get_signal())
