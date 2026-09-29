---
name: IBKR connection direction
description: User-confirmed local TWS architecture rather than assumed direct Web API OAuth.
---
The user confirmed they will run TWS locally on their own machine. Base further architecture discussions on a local execution worker connecting to TWS, not on assumed eligibility for direct Web API OAuth.

**Why:** Earlier architecture discussions assumed gateway-free OAuth access without establishing account eligibility. The user subsequently chose local TWS after reviewing the distinction between TWS/IB Gateway and Client Portal Gateway.

**How to apply:** Treat this as a target architecture, not evidence that a local worker or live broker integration has been implemented. Keep the broker socket private and distinguish TWS API connectivity from Client Portal Web API connectivity.