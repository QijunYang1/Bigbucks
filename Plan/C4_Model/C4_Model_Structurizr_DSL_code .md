```structurizr-dsl
/*
 * This is a combined version of the following workspaces, with automatic layout enabled:
 *
 * - "Big Bank plc - System Landscape" (https://structurizr.com/share/28201/)
 * - "Big Bank plc - Internet Banking System" (https://structurizr.com/share/36141/)
*/
workspace "Big Bank plc" "This is an example workspace to illustrate the key features of Structurizr, via the DSL, based around a fictional online banking system." {

    model {
        customer = person "Bigbucks Customer" "A customer of the Bigbucks, with personal accounts." "Customer"
        
        group "BigBucks" {
            admin = person "Administrator" "Administration and support staff within the Bigbucks." "Administrator"
    
            Yfinance = softwaresystem "Yahoo Finance System" "List all of the real-time and historical trading information about stocks, indices, crpto currency, etc." "Existing System"
    

            BigbucksSystem = softwaresystem "Bigbucks System" "Allows customers to view information about their trading accounts, and make payments." {
                singlePageApplication = container "Single-Page Application" "Provides all of the Bigbucks functionality to customers via their web browser." "JavaScript and HTML" "Web Browser"
                webApplication = container "Web Application" "Delivers the static content and the Bigcuks single page application." "Python and Flask"
                apiApplication = container "API Application" "Provides Bigbucks functionality via a JSON/HTTPS API." "Python and Flask" {
                    registerController = component "Register Controller" "Allows users to register in the Bigbucks System." "Authentication"
                    signinController = component "Sign In Controller" "Allows users to sign in to the Bigbucks System." "Authentication"
                    signoutController = component "Sign Out Controller" "Allows users to sign out in the Bigbucks System." "Authentication"
                    
                    
                    accountsSummaryController = component "Balance Summary Controller" "Provides customers with a summary of their balance."  "Features"
                    buysellController = component "Buy & Sell Controller" "Enable customers to buy & sell securities by using real-time price or historical price"  "Features"
                    portfolioController = component "Portfolio Controller" "Enable customers to run reports on their holdings" "Features"
                    transactionController = component "Transaction Controller" "Enable customers to know their transaction records" "Features"
                    riskreturnController = component "Risk & Return Analysis Controller" "Enable customers to analyze the risk-return profile of their portfolio" "Features"
                    chartController = component "Charting Controller" "Enable customers to consider history as they evaluate their holdings" "Features"
                    watchlistController = component "Watch List Controller" "Enable customers to customerize their watch list" "Features"
                    
                }
                database = container "Database" "Stores user registration information, hashed authentication credentials, access logs, stock data, user's portfolio info etc." "SQLite" "Database"
            }
        }

        # relationships between people and software systems
        customer -> BigbucksSystem "Views trading account balances, and makes payments using"
        admin -> BigbucksSystem "Oversee stocks and shares users owned, and dates of the order"
        BigbucksSystem -> Yfinance "Gets real-time and historical financial instrument information (e.g. price, volume) from"

        # relationships to/from containers
        customer -> webApplication "Visits bigbucks.com using" "HTTPS"
        admin -> webApplication "Visits bigbucks.com using" "HTTPS"
        webApplication -> singlePageApplication "Deliver static content and data to the customer's web browser"
        customer -> singlePageApplication "Register, log in and use multiple features by"
        admin -> singlePageApplication "Oversee the system using"
        singlePageApplication -> webApplication "Send HTTP requests to"
        webApplication -> apiApplication "Makes API calls to"
        apiApplication -> database "Get the data from"
        Yfinance -> apiApplication "Send data to "
        database -> apiApplication "Send data to"
        apiApplication -> webApplication "Sent results to"
        
        
        
        # webApplication -> singlePageApplication "Deliver static content and data to the customer's web browser"
        # customer -> singlePageApplication "Register, log in, view account balances, trades securities and analyze risk & return using"
        # admin -> singlePageApplication "Oversee the Whole portfolio the Bigbucks has using"
        # singlePageApplication -> webApplication "Request specific data and content by calling the route using "
        # webApplication -> apiApplication "Call the specific functions to fetch, process and analyze the data using"
        # apiApplication -> database "Fetch, update, delete and add data using"
        # Yfinance -> apiApplication "Deliver requested securities' data to "
        # database -> apiApplication "Send the data to"
        # apiApplication -> webApplication "Sent the processed results back to"
        
        # relationships to/from components
        webApplication -> registerController "Makes API calls to" "JSON/HTTPS"
        webApplication -> signinController "Makes API calls to" "JSON/HTTPS"
        registerController -> signinController "Sign in"
        signinController -> signoutController "Sign out"
        
        signinController -> accountsSummaryController "Uses"
        signinController -> buysellController "Uses"
        buysellController -> accountsSummaryController "Check"
        buysellController -> transactionController "Record"
        
        signinController -> portfolioController "Uses"
        signinController -> riskreturnController "Uses"
        riskreturnController -> portfolioController "Check"
        
        signinController -> chartController "Uses"
        signinController -> watchlistController "Uses"
        chartController -> watchlistController "Check"
        chartController -> riskreturnController "Uses"
        chartController -> portfolioController "Uses"
        
        accountsSummaryController -> database "Reads from and writes to" "SQL/TCP"
        buysellController -> database "Reads from and writes to" "SQL/TCP"
        buysellController -> Yfinance "Reads from" "SQL/TCP"
        portfolioController -> database "Reads from and writes to" "SQL/TCP"
        portfolioController -> Yfinance "Reads from" "SQL/TCP"
        transactionController -> database "Reads from and writes to" "SQL/TCP"
        riskreturnController -> database "Reads from and writes to" "SQL/TCP"
        chartController -> database "Reads from and writes to" "SQL/TCP"
        watchlistController -> database "Reads from and writes to" "SQL/TCP"
        watchlistController -> Yfinance "Reads from" "SQL/TCP"
    }


    views {
        systemlandscape "SystemLandscape" {
            include *
            autoLayout
        }

        systemcontext BigbucksSystem "SystemContext" {
            include *
            animation {
                BigbucksSystem
                customer
                Yfinance
                # email
            }
            autoLayout
            description "The system context diagram for the Internet Banking System."
            properties {
                structurizr.groups false
            }
        }

        container BigbucksSystem "Containers" {
            include *
            animation {
                customer Yfinance
                webApplication
                singlePageApplication
                apiApplication
                database
            }
            autoLayout
            description "The container diagram for the Internet Banking System."
        }

        component apiApplication "Components" {
            include *
            animation {
                singlePageApplication database  Yfinance
            }
            autoLayout
            description "The component diagram for the API Application."
        }


        styles {
            element "Person" {
                color #ffffff
                fontSize 22
                shape Person
            }
            element "Customer" {
                background #08427b
            }
            element "Administrator" {
                background #999999
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "Existing System" {
                background #999999
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Web Browser" {
                shape WebBrowser
            }
            element "Database" {
                shape Cylinder
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Failover" {
                opacity 25
            }
        }
    }
}
```