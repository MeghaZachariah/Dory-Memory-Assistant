import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// The same palette as the Dory website: deep navy and mint for sign-in and headers,
/// a calm mint-white page with white cards inside. Large type everywhere for older eyes.
class DoryColors {
  static const navy = Color(0xFF081C2C); // sign-in background, header band
  static const deep = Color(0xFF123141); // main text, the big Talk card, buttons
  static const mint = Color(0xFF73E5C4); // accent on dark backgrounds
  static const amber = Color(0xFFF1C86E); // the little dot on the logo
  static const onDarkMuted = Color(0xFF9BB6B9); // secondary text on navy

  static const page = Color(0xFFF7FBF8); // background
  static const card = Color(0xFFFFFFFF); // cards
  static const border = Color(0xFFDCEBE5); // card outlines
  static const ink = deep; // main text
  static const muted = Color(0xFF71898B); // secondary text
  static const eyebrow = Color(0xFF499F88); // small capital labels
  static const primary = Color(0xFF2F8D75); // links, icons, switches on light backgrounds
  static const primarySoft = Color(0xFFE9F7EF); // icon tiles, soft buttons, "Dory is here"
  static const ok = Color(0xFF5AAA8D); // connected, calls on
  static const warn = Color(0xFFC98828); // offline, gentle warnings
  static const hangUp = Color(0xFFD86D62); // end call, delete
}

const fontText = 'DMSans';
const fontDisplay = 'Fraunces';

/// Fraunces headings, like the website's "Welcome back." and "Good morning, Mary."
TextStyle display(double size, {Color color = DoryColors.ink}) => TextStyle(
      fontFamily: fontDisplay,
      fontSize: size,
      fontWeight: FontWeight.w600,
      height: 1.05,
      letterSpacing: -size * 0.04,
      color: color,
    );

/// Small capital labels above sections ("YOUR FAMILY CIRCLE").
TextStyle eyebrow({Color color = DoryColors.eyebrow}) =>
    TextStyle(fontFamily: fontText, fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 2.2, color: color);

/// Status-bar icons: dark on the light pages, light on navy.
const darkStatusBar = SystemUiOverlayStyle(
  statusBarColor: Colors.transparent,
  statusBarIconBrightness: Brightness.dark,
  statusBarBrightness: Brightness.light,
);
const lightStatusBar = SystemUiOverlayStyle(
  statusBarColor: Colors.transparent,
  statusBarIconBrightness: Brightness.light,
  statusBarBrightness: Brightness.dark,
);

ThemeData doryTheme() {
  final base = ThemeData(
    useMaterial3: true,
    fontFamily: fontText,
    colorScheme: ColorScheme.fromSeed(seedColor: DoryColors.primary).copyWith(
      primary: DoryColors.primary,
      onPrimary: Colors.white,
      surface: DoryColors.page,
      onSurface: DoryColors.ink,
      outline: DoryColors.border,
    ),
    scaffoldBackgroundColor: DoryColors.page,
  );
  final buttonShape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(18));
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: DoryColors.ink, displayColor: DoryColors.ink),
    appBarTheme: const AppBarTheme(
      backgroundColor: DoryColors.page,
      foregroundColor: DoryColors.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      systemOverlayStyle: darkStatusBar,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: DoryColors.deep,
        foregroundColor: Colors.white,
        shape: buttonShape,
        textStyle: const TextStyle(fontFamily: fontText, fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: DoryColors.deep,
        side: const BorderSide(color: DoryColors.border, width: 1.5),
        shape: buttonShape,
      ),
    ),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(foregroundColor: DoryColors.primary)),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Colors.white : null),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? DoryColors.primary : null),
    ),
    snackBarTheme: const SnackBarThemeData(backgroundColor: DoryColors.deep, behavior: SnackBarBehavior.floating),
    inputDecorationTheme: const InputDecorationTheme(filled: true, fillColor: DoryColors.card),
  );
}

/// The website's logo: a soft tile with a mint brain-circuit mark and an amber dot,
/// "Dory" in Fraunces and "MEMORY, MADE GENTLE" underneath.
class DoryLogo extends StatelessWidget {
  const DoryLogo({super.key, this.onDark = true});
  final bool onDark;

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Stack(clipBehavior: Clip.none, children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            color: onDark ? Colors.white.withValues(alpha: 0.10) : DoryColors.primarySoft,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: onDark ? Colors.white.withValues(alpha: 0.15) : DoryColors.border),
          ),
          child: Icon(Icons.psychology_outlined, color: onDark ? DoryColors.mint : DoryColors.primary, size: 24),
        ),
        Positioned(
          right: -3,
          top: -3,
          child: Container(
            width: 11,
            height: 11,
            decoration: BoxDecoration(
              color: DoryColors.amber,
              shape: BoxShape.circle,
              border: Border.all(color: onDark ? DoryColors.navy : DoryColors.page, width: 2),
            ),
          ),
        ),
      ]),
      const SizedBox(width: 12),
      Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Text('Dory', style: display(26, color: onDark ? Colors.white : DoryColors.ink)),
        const SizedBox(height: 3),
        Text('MEMORY, MADE GENTLE',
            style: eyebrow(color: onDark ? const Color(0xFF90AEB4) : DoryColors.muted).copyWith(fontSize: 9)),
      ]),
    ]);
  }
}
