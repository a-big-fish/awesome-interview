package xyz.hunaochufang.awesomeinterview;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;

/** Shared button roles for the native Android screens. */
final class NativeButtons {
    enum Role { PRIMARY, TONAL, OUTLINED, TEXT, DANGER }

    private static final int PRIMARY = Color.rgb(0, 122, 127);
    private static final int INK = Color.rgb(23, 41, 61);
    private static final int TONAL = Color.rgb(221, 245, 243);
    private static final int OUTLINE = Color.rgb(177, 197, 205);
    private static final int DANGER = Color.rgb(174, 45, 64);
    private static final int DISABLED_TEXT = Color.rgb(145, 158, 168);

    private NativeButtons() { }

    static Button make(Context context, String label, Role role) {
        Button button = new Button(context);
        button.setText(label);
        style(button, role);
        return button;
    }

    static void style(TextView view, Role role) {
        Context context = view.getContext();
        int foreground;
        int fill;
        int stroke = Color.TRANSPARENT;
        switch (role) {
            case PRIMARY:
                foreground = Color.WHITE;
                fill = PRIMARY;
                break;
            case TONAL:
                foreground = PRIMARY;
                fill = TONAL;
                break;
            case OUTLINED:
                foreground = INK;
                fill = Color.WHITE;
                stroke = OUTLINE;
                break;
            case DANGER:
                foreground = DANGER;
                fill = Color.rgb(255, 239, 241);
                break;
            default:
                foreground = PRIMARY;
                fill = Color.TRANSPARENT;
        }
        int disabledFill = role == Role.TEXT ? Color.TRANSPARENT : Color.rgb(239, 243, 245);
        StateListDrawable layers = new StateListDrawable();
        layers.addState(new int[]{-android.R.attr.state_enabled}, shape(context, disabledFill, Color.TRANSPARENT));
        layers.addState(new int[]{}, shape(context, fill, stroke));
        int rippleColor = role == Role.PRIMARY ? 0x66FFFFFF : 0x28007A7F;
        view.setBackground(new RippleDrawable(ColorStateList.valueOf(rippleColor), layers, null));
        view.setTextColor(new ColorStateList(
                new int[][]{new int[]{-android.R.attr.state_enabled}, new int[]{}},
                new int[]{DISABLED_TEXT, foreground}));
        view.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        view.setTextSize(14);
        view.setMinHeight(dp(context, 48));
        view.setMinWidth(dp(context, 48));
        view.setPadding(dp(context, 14), 0, dp(context, 14), 0);
        view.setAllCaps(false);
        view.setGravity(android.view.Gravity.CENTER);
        view.setStateListAnimator(null);
        view.setElevation(0);
        view.setClickable(true);
        view.setFocusable(true);
        if (android.os.Build.VERSION.SDK_INT >= 26) view.setDefaultFocusHighlightEnabled(true);
    }

    private static GradientDrawable shape(Context context, int fill, int stroke) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(fill);
        shape.setCornerRadius(dp(context, 12));
        if (stroke != Color.TRANSPARENT) shape.setStroke(dp(context, 1), stroke);
        return shape;
    }

    private static int dp(Context context, int value) {
        return (int) (value * context.getResources().getDisplayMetrics().density + .5f);
    }
}
