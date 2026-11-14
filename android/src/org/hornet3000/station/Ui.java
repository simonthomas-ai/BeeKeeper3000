package org.hornet3000.station;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Kleine Bausteine für die Oberfläche (ohne XML-Layouts: weniger Dinge, die auf alten Versionen schiefgehen können). */
final class Ui {
    static final int BG = Color.rgb(20, 17, 10);
    static final int AMBER = Color.rgb(242, 176, 30);
    static final int TEXT = Color.rgb(238, 230, 213);
    static final int GOOD = Color.rgb(120, 200, 120);
    static final int BAD = Color.rgb(240, 110, 90);
    static final int DIM = Color.rgb(160, 150, 130);

    private Ui() {
    }

    static int dp(Context c, int v) {
        return (int) (v * c.getResources().getDisplayMetrics().density + 0.5f);
    }

    static TextView text(Context c, String t, int sp, int color, boolean bold) {
        TextView v = new TextView(c);
        v.setText(t);
        v.setTextSize(sp);
        v.setTextColor(color);
        if (bold) {
            v.setTypeface(Typeface.DEFAULT_BOLD);
        }
        return v;
    }

    static Button button(Context c, String label, View.OnClickListener l) {
        Button b = new Button(c);
        b.setText(label);
        b.setOnClickListener(l);
        return b;
    }

    static EditText field(Context c, String value, int inputType) {
        EditText e = new EditText(c);
        e.setText(value);
        e.setInputType(inputType);
        e.setSingleLine(true);
        return e;
    }

    static LinearLayout.LayoutParams wrap(Context c, int topDp) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.FILL_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(c, topDp);
        return p;
    }

    static LinearLayout.LayoutParams weight(int w) {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, w);
    }
}
