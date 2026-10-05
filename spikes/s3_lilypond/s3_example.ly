\version "2.26.0"
% M0-S3 spike: TAB + drums + piano staff + "title — n / N" footer + Korean title.
\paper {
  #(set-paper-size "a4")
  print-page-number = ##f
  oddHeaderMarkup = \markup \null
  evenHeaderMarkup = \markup \null
  oddFooterMarkup = \markup \fill-line {
    \concat {
      "봄날의 기타 — "
      \fromproperty #'page:page-number-string
      " / "
      \page-ref #'notirua-last-page "00" "?"
    }
  }
  evenFooterMarkup = \oddFooterMarkup
}
\header {
  title = "봄날의 기타 (Spring Guitar) — Ёжик"
  subtitle = "Guitar · Bass · Drums · Piano"
  tagline = ##f
}
guitarMusic = \relative c' { \repeat unfold 24 { e8 g a b c4 <e, g c>4 } }
bassMusic = \relative c, { \repeat unfold 24 { e8 e g a c4 g4 } }
drumMusic = \drummode { \repeat unfold 24 { bd8 hh sn hh bd8 bd sn hh } }
rh = \relative c'' { \repeat unfold 24 { c4 <e g> d8 e f g } }
lh = \relative c { \repeat unfold 24 { c2 g2 } }
\score {
  <<
    \new StaffGroup \with { instrumentName = "Guitar" } <<
      \new Staff { \clef "treble_8" \key c \major \time 4/4 \tempo 4 = 120 \guitarMusic }
      \new TabStaff \with { stringTunings = #guitar-tuning } { \guitarMusic }
    >>
    \new StaffGroup \with { instrumentName = "Bass" } <<
      \new Staff { \clef "bass_8" \bassMusic }
      \new TabStaff \with { stringTunings = #bass-tuning } { \bassMusic }
    >>
    \new DrumStaff \with { instrumentName = "Drums" } { \drumMusic }
    \new PianoStaff \with { instrumentName = "Piano" } <<
      \new Staff { \rh }
      \new Staff { \clef bass \lh \label #'notirua-last-page }
    >>
  >>
  \layout { }
}
