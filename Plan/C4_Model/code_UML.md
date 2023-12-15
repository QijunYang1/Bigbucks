```
@startuml
class browser
browser--> FlaskApplication: HTTP requests
class FlaskApplication

class registerController{
Name
Password
--
ParseRequest
UpdateDatabase
}
FlaskApplication --> registerController: use


class signinController{
Name
Password
--
ParseRequest
ReturnUser
}
FlaskApplication --> signinController: use
registerController --> signinController: use


class signoutController{
ParseRequest
ReturnHomePage
}
signinController --> signoutController: use


class accountsSummaryController{
User
--
CalculateCashBalance
CalculatePortfolioBalance
CalculateTotalBalance
}
signinController --> accountsSummaryController: log in required

class buysellController{
User
--
Buy
Sell
CheckBalance
}
signinController --> buysellController: log in required
buysellController --> accountsSummaryController: check


class portfolioController{
User
--
CalculatePortfolioWeights
CalculatePortfolioVol
CalculatePortfolioReturn
CalculatePortfolioSharpeRatio
}
signinController --> portfolioController: log in required

class transactionController{
User
--
TrackTransaction
}

buysellController-> transactionController: Record


class riskreturnController{
User
--
CalculateEfficientFrontier
CalulateOptSR
}
signinController --> riskreturnController: log in required


class chartController{
User
--
FetchPlotData
PlotEfficientFrontier
PlotReturn
PlotPrice
GeneratePlotInHTMLFormat
}
signinController --> chartController: log in required
chartController --> riskreturnController: Get the optimal portfolio data
chartController --> portfolioController: Get the current portfolio data
chartController --> watchlistController: Get the latest data

class watchlistController{
User
--
AddStocks
DeleteStocks
}
signinController --> watchlistController: log in required
@enduml
```