module Main exposing (..)
import Array
import Array2D exposing (Array2D)
import Browser
import Css exposing (..)
import Html.Styled exposing (..)
import Html.Events.Extra.Mouse as Mouse
import Html.Styled.Attributes exposing (css)

boardWidth = 60
boardHeight = 30

main =
  Browser.sandbox
      { init = init
      , update = update
      , view = view >> toUnstyled
      }


type alias Cell =
    { x: Int
    , y: Int
    , is_mine: Bool
    , is_flagged: Bool
    , is_revealed: Bool
    , number: Int
    }

type alias CellGrid =
    Array2D Cell


{-| Transform a cell, returning the changed Array2D.

    transform 0 0 (\v -> v + 100) [[1, 2], [3, 4]] == [[101, 2], [3, 4]]

-}
transform : Int -> Int -> (a -> a) -> Array2D a -> Array2D a
transform row col f array2d =
    let
        v = Array2D.get row col array2d
    in
        case v of
            Nothing ->
                array2d

            Just old ->
                Array2D.set row col (f old) array2d


type alias Game =
    { cells: CellGrid
    , width: Int
    , height: Int
    }


init : Game
init =
    { cells = board boardWidth boardHeight
    , width = boardWidth
    , height = boardHeight
    }


board : Int -> Int -> CellGrid
board width height =
    Array2D.initialize
      height
      width
      (\y x -> Cell x y False False False 0)


type Msg
  = RevealCell Int Int
  | FlagCell Int Int
  | CascadeCell Int Int
  | NoOp


update : Msg -> Game -> Game
update msg game =
    case msg of
      RevealCell x y ->
          {game | cells = transform y x (\cell -> {cell | is_revealed = True}) game.cells}

      FlagCell x y ->
          {game | cells = transform y x (\cell -> {cell | is_flagged = not cell.is_flagged}) game.cells}

      CascadeCell x y ->
          -- TODO
          game

      NoOp ->
          game


view : Game -> Html Msg
view game =
    div [ css
            [ lineHeight (px 0)
            , width (px (toFloat game.width * 16))
            , height (px (toFloat game.height * 16))
            , margin2 auto auto
            ]
        ]
      (List.map
        (\row ->
          div []
            (List.map renderCell (Array.toList row)))
        (Array.toList game.cells.data))


renderCell : Cell -> Html Msg
renderCell cell =
    let
        clickHandler =
            Mouse.onClick (\event -> handleCellClick event cell)

        rightClickHandler =
            Mouse.onWithOptions
              "contextmenu"
              { stopPropagation = True
              , preventDefault = True
              }
              (\event -> handleCellClick { event | button = Mouse.SecondButton } cell)

        image =
            if cell.is_revealed then
              if cell.is_mine then
                "mine"
              else if cell.number == 0 then
                "empty"
              else
                String.fromInt cell.number
            else if cell.is_flagged then
              "flag"
            else
              "unrevealed"

    in
        button [ Html.Styled.Attributes.fromUnstyled clickHandler
               , Html.Styled.Attributes.fromUnstyled rightClickHandler
               , css
                  [ display inlineBlock
                  , backgroundImage (url ("src/images/" ++ image ++ ".png"))
                  , width (px 16)
                  , height (px 16)
                  , border (px 0)
                  , padding (px 0)
                  , lineHeight (px 0)
                  ]
               ] []


handleCellClick : Mouse.Event -> Cell -> Msg
handleCellClick event cell =
    if event.button == Mouse.MainButton then
        RevealCell cell.x cell.y
    else if event.button == Mouse.SecondButton then
        FlagCell cell.x cell.y
    else if event.button == Mouse.MiddleButton then
        CascadeCell cell.x cell.y
    else
        NoOp
