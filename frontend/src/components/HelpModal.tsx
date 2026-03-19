import { X, BookOpen, ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useTheme } from '../lib/theme'

interface HelpModalProps {
  onClose: () => void
}

interface Term {
  term: string
  short?: string
  definition: string
  example?: string
}

interface Section {
  title: string
  terms: Term[]
}

const sections: Section[] = [
  {
    title: 'Risk & Return Metrics',
    terms: [
      {
        term: 'Sharpe Ratio',
        definition: 'Measures how much return you earn per unit of risk. A higher Sharpe ratio means better risk-adjusted performance.',
        example: 'A Sharpe ratio of 1.0 is good, 2.0 is great. Anything below 0 means your returns are worse than a risk-free investment.'
      },
      {
        term: 'Expected Return',
        definition: 'The estimated annual profit your portfolio is projected to earn, expressed as a percentage. Based on historical price data using geometric (log) returns.',
        example: 'An expected return of 12% means your $10,000 investment is projected to grow by $1,200 in a year.'
      },
      {
        term: 'Volatility',
        definition: 'How much your portfolio\'s value swings up and down. Higher volatility means bigger price movements — both gains and losses.',
        example: 'A volatility of 20% means the portfolio\'s annual return could vary by roughly ±20% from the expected return.'
      },
      {
        term: 'Value at Risk (VaR)',
        short: 'VaR',
        definition: 'The maximum expected loss over a given time period at a 95% confidence level. Basically, the worst expected daily loss 95% of the time.',
        example: 'A VaR of -2.5% means on 95% of days you would not lose more than 2.5% of your portfolio value.'
      },
      {
        term: 'Max Drawdown',
        definition: 'The largest peak-to-trough decline in portfolio value over a period. Tells you the worst historical loss if you had bought at the top and sold at the bottom.',
        example: 'A max drawdown of -30% means the portfolio once fell 30% from its highest point before recovering.'
      },
      {
        term: 'Beta',
        definition: 'Measures how much your portfolio moves relative to the overall market. A beta of 1 means it moves with the market; above 1 is more volatile; below 1 is more stable.',
        example: 'If the market falls 10% and your portfolio has a beta of 1.5, you\'d expect a fall of roughly 15%.'
      },
    ]
  },
  {
    title: 'Technical Indicators',
    terms: [
      {
        term: 'Relative Strength Index (RSI)',
        short: 'RSI',
        definition: 'A momentum indicator (0–100) that shows whether a stock is overbought or oversold. Below 30 = oversold (potential buy), above 70 = overbought (potential sell).',
        example: 'RSI of 20 = strongly oversold, possible buying opportunity. RSI of 80 = strongly overbought, possible selling signal.'
      },
      {
        term: 'Moving Average Convergence Divergence (MACD)',
        short: 'MACD',
        definition: 'Tracks the relationship between two moving averages of a stock\'s price. When the MACD line crosses above the signal line it\'s bullish (buy signal); crossing below is bearish (sell signal).',
        example: 'A bullish MACD crossover suggests upward momentum is building and the stock may be starting a new uptrend.'
      },
      {
        term: 'Bollinger Bands',
        definition: 'Three lines plotted around the price: a middle moving average and upper/lower bands two standard deviations away. When price touches the lower band it may be oversold; upper band may be overbought.',
        example: 'If a stock price drops to the lower Bollinger Band, it may be a sign to consider buying.'
      },
      {
        term: 'Simple Moving Average (SMA)',
        short: 'SMA',
        definition: 'The average closing price over a set number of days (e.g., 20-day or 50-day). Used to smooth out price fluctuations and identify trends.',
        example: 'When a stock price rises above its 50-day SMA, it often signals a positive trend.'
      },
      {
        term: 'Exponential Moving Average (EMA)',
        short: 'EMA',
        definition: 'Similar to SMA but gives more weight to recent prices, making it more responsive to new information.',
        example: 'EMA reacts faster to recent price changes than SMA, which can help catch trend changes earlier.'
      },
    ]
  },
  {
    title: 'Portfolio Strategies',
    terms: [
      {
        term: 'Modern Portfolio Theory (MPT)',
        short: 'MPT',
        definition: 'An investment framework by Harry Markowitz that shows how to build a portfolio of assets to maximise return for a given level of risk by taking advantage of diversification.',
        example: 'Combining assets that don\'t move together (low correlation) reduces overall portfolio risk without sacrificing returns.'
      },
      {
        term: 'Capital Asset Pricing Model (CAPM)',
        short: 'CAPM',
        definition: 'A model that describes the relationship between systematic risk and expected return. It helps estimate what return you should expect given a stock\'s risk (beta) relative to the market.',
        example: 'A stock with a beta of 1.5 and a market return of 8% would have an expected return of around 11% (using CAPM).'
      },
      {
        term: 'Efficient Frontier',
        definition: 'The set of optimal portfolios that offer the highest expected return for a given level of risk. Portfolios on the efficient frontier are perfectly balanced.',
        example: 'Sapient\'s optimizer finds the point on the efficient frontier that maximises the Sharpe ratio.'
      },
      {
        term: 'Diversification',
        definition: 'Spreading investments across different stocks, sectors, and asset types so that a loss in one area doesn\'t devastate the whole portfolio.',
        example: 'Owning both mining stocks and healthcare stocks means a mining downturn won\'t wipe out your entire portfolio.'
      },
      {
        term: 'Rebalancing',
        definition: 'Adjusting your portfolio back to its target weights after market movements have caused it to drift. Ensures you\'re not over-exposed to one stock.',
        example: 'If CBA grows to 40% of your portfolio but the target is 25%, you\'d sell some CBA to rebalance.'
      },
    ]
  },
  {
    title: 'Fundamental Analysis',
    terms: [
      {
        term: 'Price-to-Earnings Ratio (P/E)',
        short: 'P/E',
        definition: 'The stock price divided by the company\'s annual earnings per share. Shows how much investors pay for each dollar of earnings. Lower P/E can indicate better value.',
        example: 'A P/E of 15 means investors pay $15 for every $1 of profit the company earns.'
      },
      {
        term: 'Earnings Yield',
        definition: 'The inverse of the P/E ratio (earnings per share divided by price). Higher earnings yield means you\'re getting more earnings for each dollar invested.',
        example: 'An earnings yield of 6% on a stock means you earn $6 of profits per $100 invested — comparable to a 6% interest rate.'
      },
      {
        term: 'Return on Equity (ROE)',
        short: 'ROE',
        definition: 'How efficiently a company uses shareholders\' money to generate profit. Higher ROE means the company is generating more profit from the same equity base.',
        example: 'An ROE of 20% means the company earns 20 cents of profit for every $1 of shareholders\' funds.'
      },
      {
        term: 'Dividend Yield',
        definition: 'The annual dividend payment divided by the stock price, expressed as a percentage. Tells you how much income you receive relative to what you paid for the stock.',
        example: 'If a stock pays $2/year in dividends and costs $40, the dividend yield is 5%.'
      },
      {
        term: 'Market Capitalisation (Market Cap)',
        short: 'Market Cap',
        definition: 'The total value of all a company\'s shares — calculated as share price × number of shares. Indicates the overall size of the company.',
        example: 'A market cap of $10 billion means the market values the whole company at $10 billion.'
      },
    ]
  },
  {
    title: 'Markets & Indices',
    terms: [
      {
        term: 'ASX 200',
        definition: 'The Australian Securities Exchange\'s benchmark index tracking the 200 largest companies listed in Australia by market capitalisation.',
        example: 'Companies like BHP, CBA, and CSL are included in the ASX 200.'
      },
      {
        term: 'S&P 500',
        definition: 'The Standard & Poor\'s 500, a US benchmark index tracking the 500 largest publicly traded companies in America. Widely used as a proxy for the US stock market.',
        example: 'Companies like Apple, Microsoft, and Amazon are in the S&P 500.'
      },
      {
        term: 'Risk-Free Rate',
        definition: 'The theoretical return of an investment with zero risk, typically based on government bond yields. Used as a baseline for comparing risky investments.',
        example: 'Sapient uses the Australian 10-year government bond yield (~4.35%) as the risk-free rate for ASX portfolios.'
      },
      {
        term: 'Benchmark',
        definition: 'A standard index used to compare your portfolio\'s performance. If your portfolio outperforms the benchmark, you\'re doing better than "the market".',
        example: 'For ASX portfolios, the ASX 200 (^AXJO) is the typical benchmark. For US portfolios, the S&P 500.'
      },
    ]
  },
]

export default function HelpModal({ onClose }: HelpModalProps) {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [openSection, setOpenSection] = useState<string | null>('Technical Indicators')
  const [search, setSearch] = useState('')

  const filteredSections = sections.map(section => ({
    ...section,
    terms: section.terms.filter(t =>
      !search ||
      t.term.toLowerCase().includes(search.toLowerCase()) ||
      (t.short && t.short.toLowerCase().includes(search.toLowerCase())) ||
      t.definition.toLowerCase().includes(search.toLowerCase())
    )
  })).filter(s => s.terms.length > 0)

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div
        className={`rounded-2xl border w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl ${
          isDark ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-200'
        }`}
      >
        <div className={`flex items-center justify-between p-5 border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-500/20 rounded-xl border border-sky-500/30">
              <BookOpen className="w-5 h-5 text-sky-400" />
            </div>
            <div>
              <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Help & Glossary</h2>
              <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>Explanations for financial terms and acronyms</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`p-2 rounded-lg transition-colors ${isDark ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className={`px-5 pt-4 pb-2 border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
          <input
            type="text"
            placeholder="Search terms (e.g. RSI, Sharpe, CAPM...)"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="input w-full"
          />
        </div>

        <div className="overflow-y-auto flex-1 p-5 space-y-2">
          {filteredSections.length === 0 ? (
            <div className="text-center py-8 text-slate-500">No matching terms found.</div>
          ) : (
            filteredSections.map(section => (
              <div key={section.title} className={`rounded-xl border overflow-hidden ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                <button
                  onClick={() => setOpenSection(openSection === section.title ? null : section.title)}
                  className={`w-full flex items-center justify-between px-4 py-3 text-left transition-colors ${
                    isDark ? 'hover:bg-slate-800/50' : 'hover:bg-slate-50'
                  }`}
                >
                  <span className={`font-semibold text-sm ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{section.title}</span>
                  {openSection === section.title
                    ? <ChevronDown className="w-4 h-4 text-slate-400" />
                    : <ChevronRight className="w-4 h-4 text-slate-400" />
                  }
                </button>
                {(openSection === section.title || search) && (
                  <div className={`border-t divide-y ${isDark ? 'border-slate-700/50 divide-slate-700/30' : 'border-slate-200 divide-slate-100'}`}>
                    {section.terms.map(term => (
                      <div key={term.term} className={`px-4 py-3 ${isDark ? 'bg-slate-800/20' : 'bg-slate-50/50'}`}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`font-medium text-sm ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{term.term}</span>
                          {term.short && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-700 dark:text-sky-400 border border-sky-500/30 font-mono">
                              {term.short}
                            </span>
                          )}
                        </div>
                        <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{term.definition}</p>
                        {term.example && (
                          <p className={`text-xs mt-1.5 italic ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
                            Example: {term.example}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
