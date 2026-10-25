package dev.local.notificationbridge;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.RemoteViews;
import android.widget.TextView;

public class MainActivity extends Activity {
    private static final String CHANNEL = "bridge_test";
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(40, 70, 40, 40);
        TextView text = new TextView(this);
        text.setText("Notification Bridge\n\nStreams notification changes to your computer over USB/ADB. "
            + "Custom notification views are read off screen.\n\n"
            + "Notification data stays in this app's private storage and on your computer. "
            + "This app has no internet permission.\n\n"
            + "Enable notification access below, then use the Python listener on your computer.");
        text.setTextSize(18);
        layout.addView(text);
        Button access = new Button(this);
        access.setText("Notification access settings");
        access.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        layout.addView(access);
        Button demo = new Button(this);
        demo.setText("Test a live notification");
        demo.setOnClickListener(v -> demo());
        layout.addView(demo);
        setContentView(layout);
        if (getIntent().getBooleanExtra("demo", false)) demo();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (intent.getBooleanExtra("demo", false)) demo();
    }

    private void demo() {
        handler.removeCallbacksAndMessages(null);
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Listener test", NotificationManager.IMPORTANCE_LOW));
        postDemo("Finding your driver", 10);
        handler.postDelayed(() -> postDemo("Driver is on the way", 55), 3000);
        handler.postDelayed(() -> postDemo("Driver has arrived", 100), 6000);
        handler.postDelayed(() -> manager.cancel(7001), 9000);
    }

    private void postDemo(String status, int progress) {
        // Deliberately omit EXTRA_TITLE and EXTRA_TEXT, just like Gojek's custom view.
        RemoteViews view = new RemoteViews(getPackageName(), R.layout.live_demo);
        view.setTextViewText(R.id.demo_title, "Live activity test");
        view.setTextViewText(R.id.demo_status, status);
        view.setProgressBar(R.id.demo_progress, 100, progress, false);
        Notification notification = new Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setCustomContentView(view)
            .setCustomBigContentView(view)
            .setStyle(new Notification.DecoratedCustomViewStyle())
            .setProgress(100, progress, false)
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .build();
        getSystemService(NotificationManager.class).notify(7001, notification);
    }
}
