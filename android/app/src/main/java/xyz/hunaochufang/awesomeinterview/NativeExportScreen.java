package xyz.hunaochufang.awesomeinterview;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.pdf.PdfRenderer;
import android.os.ParcelFileDescriptor;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.ArrayAdapter;
import android.widget.TextView;

import java.io.File;
import java.io.IOException;

/** Renders one export PDF page at a time, sized for phone review and image sharing. */
final class NativeExportScreen extends LinearLayout {
    interface Actions {
        void refresh();
        void savePage();
        void savePdf();
        void back();
    }

    private final Actions actions;
    private final Spinner style;
    private final CheckBox hideOnSite;
    private final CheckBox hideReview;
    private final CheckBox hideInterviewer;
    private final CheckBox hideCompany;
    private final CheckBox hidePosition;
    private final CheckBox hideInterviewTime;
    private final ImageView preview;
    private final TextView status;
    private final Button previous;
    private final Button next;
    private final Button savePage;
    private final Button savePdf;
    private PdfRenderer renderer;
    private ParcelFileDescriptor descriptor;
    private Bitmap pageBitmap;
    private File pdfFile;
    private int pageIndex;

    NativeExportScreen(Context context, Actions actions) {
        super(context);
        this.actions = actions;
        setOrientation(VERTICAL);
        setBackgroundColor(Color.rgb(246, 248, 252));
        setPadding(dp(14), dp(10), dp(14), dp(8));
        LinearLayout heading = new LinearLayout(context);
        heading.setGravity(Gravity.CENTER_VERTICAL);
        TextView title = new TextView(context);
        title.setText("面经导出 · 逐页预览");
        title.setTextSize(19);
        title.setTypeface(null, Typeface.BOLD);
        title.setTextColor(Color.rgb(18, 33, 64));
        heading.addView(title, new LayoutParams(0, dp(46), 1));
        Button back = button("返回");
        back.setOnClickListener(v -> actions.back());
        heading.addView(back);
        addView(heading);

        ScrollView optionsScroll = new ScrollView(context);
        LinearLayout options = new LinearLayout(context);
        options.setOrientation(VERTICAL);
        optionsScroll.addView(options);
        addView(optionsScroll, new LayoutParams(-1, dp(150)));
        style = new Spinner(context);
        style.setAdapter(new ArrayAdapter<>(context, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"简洁线条", "扁平列表"}));
        options.addView(style);
        hideOnSite = option(options, "隐藏现场回答");
        hideReview = option(options, "隐藏复盘答案");
        hideInterviewer = option(options, "隐藏面试官回答");
        hideCompany = option(options, "隐藏公司");
        hidePosition = option(options, "隐藏岗位");
        hideInterviewTime = option(options, "隐藏面试时间");
        Button hideAll = button("隐藏所有回答和面试时间");
        hideAll.setOnClickListener(v -> {
            hideOnSite.setChecked(true);
            hideReview.setChecked(true);
            hideInterviewer.setChecked(true);
            hideInterviewTime.setChecked(true);
            actions.refresh();
        });
        options.addView(hideAll);
        Button update = button("更新预览");
        update.setOnClickListener(v -> actions.refresh());
        options.addView(update);

        preview = new ImageView(context);
        preview.setScaleType(ImageView.ScaleType.FIT_CENTER);
        preview.setBackgroundColor(Color.WHITE);
        addView(preview, new LayoutParams(-1, 0, 1));
        status = new TextView(context);
        status.setGravity(Gravity.CENTER);
        status.setTextColor(Color.rgb(70, 86, 110));
        status.setText("正在生成预览…");
        addView(status, new LayoutParams(-1, dp(32)));
        LinearLayout controls = new LinearLayout(context);
        previous = button("上一页");
        next = button("下一页");
        previous.setOnClickListener(v -> renderPage(pageIndex - 1));
        next.setOnClickListener(v -> renderPage(pageIndex + 1));
        controls.addView(previous, new LayoutParams(0, dp(44), 1));
        controls.addView(next, new LayoutParams(0, dp(44), 1));
        addView(controls);
        LinearLayout saves = new LinearLayout(context);
        savePage = button("保存本页图片");
        savePdf = button("保存整份 PDF");
        savePage.setOnClickListener(v -> actions.savePage());
        savePdf.setOnClickListener(v -> actions.savePdf());
        saves.addView(savePage, new LayoutParams(0, dp(44), 1));
        saves.addView(savePdf, new LayoutParams(0, dp(44), 1));
        addView(saves);
        updateButtons();
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + .5f);
    }

    private Button button(String label) {
        Button value = new Button(getContext());
        value.setText(label);
        value.setAllCaps(false);
        value.setTextSize(12);
        return value;
    }

    private CheckBox option(LinearLayout parent, String label) {
        CheckBox value = new CheckBox(getContext());
        value.setText(label);
        parent.addView(value);
        return value;
    }

    String query() {
        return "style=" + (style.getSelectedItemPosition() == 0 ? "lines" : "flat") +
                "&hide_on_site_answer=" + hideOnSite.isChecked() +
                "&hide_review_answer=" + hideReview.isChecked() +
                "&hide_interviewer_answer=" + hideInterviewer.isChecked() +
                "&hide_company=" + hideCompany.isChecked() +
                "&hide_position=" + hidePosition.isChecked() +
                "&hide_interviewed_at=" + hideInterviewTime.isChecked();
    }

    void setLoading() {
        status.setText("正在生成预览…");
        savePage.setEnabled(false);
        savePdf.setEnabled(false);
    }

    void setError(String message) {
        status.setText(message);
        updateButtons();
    }

    void open(File file) throws IOException {
        close();
        try {
            pdfFile = file;
            descriptor = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
            renderer = new PdfRenderer(descriptor);
            if (renderer.getPageCount() == 0) throw new IOException("导出文件没有可展示的页面");
            renderPage(0);
        } catch (IOException | RuntimeException error) {
            close();
            throw error;
        }
    }

    private void renderPage(int index) {
        if (renderer == null || index < 0 || index >= renderer.getPageCount()) return;
        pageIndex = index;
        PdfRenderer.Page page = renderer.openPage(index);
        try {
            int width = Math.min(2400, Math.max(1200, page.getWidth() * 2));
            int height = Math.round((float) page.getHeight() * width / page.getWidth());
            Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            bitmap.eraseColor(Color.WHITE);
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
            preview.setImageBitmap(bitmap);
            if (pageBitmap != null) pageBitmap.recycle();
            pageBitmap = bitmap;
            status.setText("第 " + (index + 1) + " / " + renderer.getPageCount() + " 页");
            updateButtons();
        } finally {
            page.close();
        }
    }

    private void updateButtons() {
        previous.setEnabled(renderer != null && pageIndex > 0);
        next.setEnabled(renderer != null && pageIndex + 1 < renderer.getPageCount());
        savePage.setEnabled(pageBitmap != null);
        savePdf.setEnabled(pdfFile != null);
    }

    Bitmap bitmap() { return pageBitmap; }
    File pdfFile() { return pdfFile; }
    int pageNumber() { return pageIndex + 1; }

    void close() {
        preview.setImageDrawable(null);
        if (pageBitmap != null) { pageBitmap.recycle(); pageBitmap = null; }
        if (renderer != null) { renderer.close(); renderer = null; }
        if (descriptor != null) { try { descriptor.close(); } catch (IOException ignored) { } descriptor = null; }
        if (pdfFile != null) { pdfFile.delete(); pdfFile = null; }
        updateButtons();
    }
}
