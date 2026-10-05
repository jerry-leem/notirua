\version "2.26.0"
\paper {
  #(set-paper-size "letter")
  print-page-number = ##f
  oddHeaderMarkup = \markup \null
  evenHeaderMarkup = \markup \null
  oddFooterMarkup = \markup \fill-line { \concat {
    "Snapshot 한글 — " \fromproperty #'page:page-number-string " / " \page-ref #'notirua-last-page "00" "?" } }
  evenFooterMarkup = \oddFooterMarkup
}
\header {
  title = "Snapshot 한글"
  subtitle = "Vocals · Guitar · Piano · Drums"
  subsubtitle = "♩ = 96 · G major"
  tagline = ##f
}
\score {
  <<
\new Staff \with { instrumentName = "Vocals" } { \clef "treble" \time 4/4 \key g \major \tempo 4 = 96
    g'4 fis'4 d'2 | \label #'notirua-last-page }
\new StaffGroup \with { instrumentName = "Guitar" } <<
  \new Staff \with { \omit StringNumber } { \clef "treble_8" \time 4/4 \key g \major
    g4\3 b4\2 r2 | }
  \new TabStaff \with { stringTunings = \stringTuning <e, a, d g b e'> } { \time 4/4 \key g \major
    g4\3 b4\2 r2 | }
>>
\new PianoStaff \with { instrumentName = "Piano" } <<
  \new Staff { \clef treble \time 4/4 \key g \major
    d''1 | }
  \new Staff { \clef bass \time 4/4 \key g \major
    g,1 | }
>>
\new DrumStaff \with { instrumentName = "Drums" } \drummode { \time 4/4
    <bd hh>4 sn4 r2 | }
  >>
  \layout { }
}
