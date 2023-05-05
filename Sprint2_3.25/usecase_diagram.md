@startuml
skinparam actorStyle awesome
left to right direction
package People{
  actor visitor as g
  actor user as u
  actor admin as A
}
package Administrator_Account {
(Create Account and View Account) 
(add and remove users) 
(manage the application' s lnusers and their portfolios)
A->Administrator_Account
}
package User_Account {
  usecase "list owned stocks"
  usecase "view history" as history
  usecase "analyze risk-return" as analyze
  usecase "report holdings" as report
(View Portfolio)
u->User_Account
(Buy/Sell Securities)
(Withdraw Funds)
usecase "Place order" 
  usecase "Buy shares" 
  usecase "Sell shares"
  usecase "portfolio risk and return profile"
}
package database{
(Store Historical Data)
}
BigBucks->database
(People)<-- :BigBucks: :send alerts for price changes or other events related to the securities lnusers are interested in

(Buy shares) ..> (Place order):extends
(Sell shares) ..> (Place order):extends

@enduml