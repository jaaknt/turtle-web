<!-- The caveats from docs/specs/portfolio.md, "The return model". Keep the two in step. -->
<template>
  <footer class="page-footer">
    <ul>
      <li>
        <strong>Time-weighted returns.</strong> They measure the holdings, not the account: buys and
        sells are cash flows, not gains or losses. There is still no cash, so there is no cash drag
        either.
      </li>
      <li>
        <strong>Annualised figures need a year.</strong> CAGR, volatility, Sharpe, Sortino and Calmar
        from under a year of data are unreliable; they are shown, flagged "&lt; 1 year", rather than
        hidden.
      </li>
      <li>
        <strong>Day one is measured differently.</strong> The portfolio runs from fill price to close,
        each benchmark not at all (it is bought at that close). Over a short history this one day can
        move the comparison.
      </li>
      <li>
        <strong>Benchmarks are buy and hold</strong> from the first day's close, as quantstats compares
        them, not the Portfolio page's shadow benchmarks, which follow your cash flows.
      </li>
    </ul>
  </footer>
</template>
