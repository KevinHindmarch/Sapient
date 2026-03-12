export interface GlossaryTerm {
  term: string
  short?: string
  definition: string
  example?: string
}

export const glossaryTerms: Record<string, GlossaryTerm> = {
  'RSI': {
    term: 'Relative Strength Index',
    short: 'RSI',
    definition: 'A momentum indicator (0–100) that shows whether a stock is overbought or oversold. Below 30 = oversold (potential buy), above 70 = overbought (potential sell).',
    example: 'RSI of 20 = strongly oversold, possible buy. RSI of 80 = strongly overbought, possible sell.'
  },
  'MACD': {
    term: 'Moving Average Convergence Divergence',
    short: 'MACD',
    definition: 'Tracks the relationship between two moving averages of a stock\'s price. When the MACD line crosses above the signal line it\'s bullish (buy signal); crossing below is bearish (sell signal).',
    example: 'A bullish MACD crossover suggests upward momentum is building.'
  },
  'Bollinger Bands': {
    term: 'Bollinger Bands',
    definition: 'Three lines around the price: a middle moving average and upper/lower bands two standard deviations away. Price near the lower band may be oversold; near the upper band may be overbought.',
    example: 'If price drops to the lower Bollinger Band, it may be a sign to consider buying.'
  },
  'SMA': {
    term: 'Simple Moving Average',
    short: 'SMA',
    definition: 'The average closing price over a set number of days (e.g., 20-day or 50-day SMA). Used to smooth out price fluctuations and identify trends.',
    example: 'When price rises above its 50-day SMA, it often signals a positive trend.'
  },
  'Sharpe Ratio': {
    term: 'Sharpe Ratio',
    definition: 'Measures how much return you earn per unit of risk. A higher Sharpe ratio means better risk-adjusted performance.',
    example: 'A Sharpe ratio of 1.0 is good, 2.0 is great. Below 0 means worse returns than a risk-free investment.'
  },
  'Expected Return': {
    term: 'Expected Return',
    definition: 'The estimated annual profit your portfolio is projected to earn, expressed as a percentage. Based on historical price data using geometric (log) returns.',
    example: 'Expected return of 12% means your $10,000 is projected to grow by $1,200 per year.'
  },
  'Volatility': {
    term: 'Volatility',
    definition: 'How much your portfolio\'s value swings up and down. Higher volatility means bigger price movements — both gains and losses.',
    example: 'A volatility of 20% means annual returns could vary by roughly ±20% from the expected return.'
  },
  'VaR': {
    term: 'Value at Risk',
    short: 'VaR',
    definition: 'The maximum expected loss over a given period at a 95% confidence level — the worst expected daily loss 95% of the time.',
    example: 'A VaR of -2.5% means on 95% of days you would not lose more than 2.5% of your portfolio value.'
  },
  'Max Drawdown': {
    term: 'Max Drawdown',
    definition: 'The largest peak-to-trough decline in portfolio value over a period. Tells you the worst historical loss if you bought at the top and sold at the bottom.',
    example: 'A max drawdown of -30% means the portfolio once fell 30% from its highest point before recovering.'
  },
  'Beta': {
    term: 'Beta',
    definition: 'Measures how much your portfolio moves relative to the overall market. Beta of 1 = moves with the market; above 1 = more volatile; below 1 = more stable.',
    example: 'If the market falls 10% and your beta is 1.5, you\'d expect a fall of roughly 15%.'
  },
  'CAPM': {
    term: 'Capital Asset Pricing Model',
    short: 'CAPM',
    definition: 'A model that describes the relationship between systematic risk and expected return. Helps estimate what return you should expect given a stock\'s risk (beta) relative to the market.',
    example: 'A stock with beta 1.5 and market return 8% would have an expected CAPM return of around 11%.'
  },
  'MPT': {
    term: 'Modern Portfolio Theory',
    short: 'MPT',
    definition: 'An investment framework that shows how to build a portfolio to maximise return for a given level of risk by taking advantage of diversification.',
    example: 'Combining assets that don\'t move together (low correlation) reduces overall risk without sacrificing returns.'
  },
  'Efficient Frontier': {
    term: 'Efficient Frontier',
    definition: 'The set of optimal portfolios that offer the highest expected return for a given level of risk. Sapient\'s optimizer finds the point that maximises the Sharpe ratio.',
    example: 'Any portfolio below the efficient frontier is suboptimal — you could get more return for the same risk.'
  },
  'Dividend Yield': {
    term: 'Dividend Yield',
    definition: 'The annual dividend payment divided by the stock price, expressed as a percentage. Tells you how much income you receive relative to what you paid for the stock.',
    example: 'If a stock pays $2/year in dividends and costs $40, the dividend yield is 5%.'
  },
  'P/E': {
    term: 'Price-to-Earnings Ratio',
    short: 'P/E',
    definition: 'The stock price divided by the company\'s annual earnings per share. Lower P/E can indicate better value.',
    example: 'A P/E of 15 means investors pay $15 for every $1 of profit the company earns.'
  },
  'ROE': {
    term: 'Return on Equity',
    short: 'ROE',
    definition: 'How efficiently a company uses shareholders\' money to generate profit. Higher ROE means the company generates more profit from the same equity base.',
    example: 'An ROE of 20% means the company earns 20 cents of profit for every $1 of shareholders\' funds.'
  },
  'Market Cap': {
    term: 'Market Capitalisation',
    short: 'Market Cap',
    definition: 'The total value of all a company\'s shares — calculated as share price × number of shares. Indicates the overall size of the company.',
    example: 'A market cap of $10 billion means the market values the whole company at $10 billion.'
  },
  'ASX 200': {
    term: 'ASX 200',
    definition: 'The Australian Securities Exchange\'s benchmark index tracking the 200 largest companies listed in Australia by market capitalisation.',
    example: 'Companies like BHP, CBA, and CSL are included in the ASX 200.'
  },
  'Risk-Free Rate': {
    term: 'Risk-Free Rate',
    definition: 'The theoretical return of an investment with zero risk, based on government bond yields. Used as a baseline for comparing risky investments.',
    example: 'Sapient uses the Australian 10-year bond yield (~4.35%) as the risk-free rate for ASX portfolios.'
  },
  'Correlation': {
    term: 'Correlation',
    definition: 'Measures how closely two stocks move together. Values range from -1 (move opposite) to +1 (move in lockstep). Lower correlation between stocks = better diversification.',
    example: 'Two mining stocks might have correlation 0.8 (highly correlated), meaning when one falls, the other likely will too.'
  },
}

export const sections = [
  {
    title: 'Technical Indicators',
    keys: ['RSI', 'MACD', 'Bollinger Bands', 'SMA']
  },
  {
    title: 'Risk & Return Metrics',
    keys: ['Sharpe Ratio', 'Expected Return', 'Volatility', 'VaR', 'Max Drawdown', 'Beta']
  },
  {
    title: 'Portfolio Strategies',
    keys: ['CAPM', 'MPT', 'Efficient Frontier', 'Correlation']
  },
  {
    title: 'Fundamental Analysis',
    keys: ['Dividend Yield', 'P/E', 'ROE', 'Market Cap']
  },
  {
    title: 'Markets',
    keys: ['ASX 200', 'Risk-Free Rate']
  },
]
