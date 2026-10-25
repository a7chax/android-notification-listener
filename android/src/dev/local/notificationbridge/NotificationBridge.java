package dev.local.notificationbridge;

import android.app.Notification;
import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.RemoteViews;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.UUID;

/** Local-only notification lifecycle journal, read by the desktop via adb run-as. */
public class NotificationBridge extends NotificationListenerService {
    private final Map<String, JSONObject> active = new LinkedHashMap<>();
    private final ArrayDeque<JSONObject> events = new ArrayDeque<>();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private String session = UUID.randomUUID().toString();
    private long sequence = 0;
    private boolean connected = false;
    private final Runnable heartbeat = new Runnable() {
        @Override public void run() {
            publish();
            handler.postDelayed(this, 5000);
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        handler.post(heartbeat);
    }

    @Override public void onListenerConnected() {
        session = UUID.randomUUID().toString();
        sequence = 0;
        events.clear();
        active.clear();
        StatusBarNotification[] notifications = getActiveNotifications();
        if (notifications != null) {
            for (StatusBarNotification sbn : notifications) active.put(sbn.getKey(), extract(sbn));
        }
        connected = true;
        publish();
    }

    @Override public void onNotificationPosted(StatusBarNotification sbn) {
        if (!connected) return;
        JSONObject record = extract(sbn);
        String type = active.containsKey(sbn.getKey()) ? "updated" : "posted";
        active.put(sbn.getKey(), record);
        append(type, record, null);
    }

    @Override public void onNotificationRemoved(StatusBarNotification sbn, RankingMap ranking, int reason) {
        if (!connected) return;
        JSONObject previous = active.remove(sbn.getKey());
        // Removal callbacks can contain light notifications without their custom views.
        append("removed", previous != null ? previous : extract(sbn), reason);
    }

    @Override public void onListenerDisconnected() {
        connected = false;
        publish();
    }

    @Override public void onDestroy() {
        handler.removeCallbacks(heartbeat);
        connected = false;
        publish();
        super.onDestroy();
    }

    private void append(String type, JSONObject record, Integer reason) {
        try {
            JSONObject event = new JSONObject();
            event.put("seq", ++sequence);
            event.put("event", type);
            event.put("timestamp", System.currentTimeMillis());
            event.put("notification", record);
            if (reason != null) event.put("removal_reason", reason);
            events.addLast(event);
            while (events.size() > 256) events.removeFirst();
            publish();
        } catch (JSONException e) {
            Log.e("NotificationBridge", "Cannot encode event", e);
        }
    }

    private void publish() {
        File file = new File(getFilesDir(), "state.json");
        File temporary = new File(getFilesDir(), "state.json.tmp");
        try {
            JSONObject state = new JSONObject();
            state.put("version", 1);
            state.put("session", session);
            state.put("seq", sequence);
            state.put("connected", connected);
            state.put("heartbeat", System.currentTimeMillis());
            state.put("active", new JSONArray(active.values()));
            state.put("events", new JSONArray(events));
            // Older framework AtomicFile versions expose a partly written base file
            // to raw readers. Close a sibling file before its atomic Linux rename.
            try (FileOutputStream output = new FileOutputStream(temporary)) {
                output.write(state.toString().getBytes(StandardCharsets.UTF_8));
                output.getFD().sync();
            }
            if (!temporary.renameTo(file)) throw new IOException("Cannot publish state.json");
        } catch (Exception e) {
            Log.e("NotificationBridge", "Cannot publish state", e);
        }
    }

    private static void putText(JSONObject out, String key, CharSequence value) throws JSONException {
        out.put(key, value == null ? JSONObject.NULL : value.toString());
    }

    private JSONObject extract(StatusBarNotification sbn) {
        JSONObject out = new JSONObject();
        try {
            Notification n = sbn.getNotification();
            Bundle extras = n.extras != null ? n.extras : Bundle.EMPTY;
            out.put("key", sbn.getKey());
            out.put("package", sbn.getPackageName());
            out.put("id", sbn.getId());
            out.put("tag", sbn.getTag() == null ? JSONObject.NULL : sbn.getTag());
            out.put("post_time", sbn.getPostTime());
            out.put("channel", n.getChannelId());
            out.put("ongoing", (n.flags & Notification.FLAG_ONGOING_EVENT) != 0);
            out.put("group_summary", (n.flags & Notification.FLAG_GROUP_SUMMARY) != 0);
            putText(out, "title", extras.getCharSequence(Notification.EXTRA_TITLE));
            putText(out, "text", extras.getCharSequence(Notification.EXTRA_TEXT));
            putText(out, "big_text", extras.getCharSequence(Notification.EXTRA_BIG_TEXT));
            putText(out, "sub_text", extras.getCharSequence(Notification.EXTRA_SUB_TEXT));
            JSONArray lines = new JSONArray();
            CharSequence[] textLines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
            if (textLines != null) for (CharSequence text : textLines) if (text != null) lines.put(text.toString());
            out.put("lines", lines);
            JSONObject progress = new JSONObject();
            progress.put("value", extras.getInt(Notification.EXTRA_PROGRESS));
            progress.put("max", extras.getInt(Notification.EXTRA_PROGRESS_MAX));
            progress.put("indeterminate", extras.getBoolean(Notification.EXTRA_PROGRESS_INDETERMINATE));
            out.put("progress", progress);

            LinkedHashSet<String> texts = new LinkedHashSet<>();
            JSONArray views = new JSONArray();
            JSONArray viewProgress = new JSONArray();
            JSONArray errors = new JSONArray();
            boolean custom = n.contentView != null || n.bigContentView != null || n.headsUpContentView != null;
            out.put("custom_view", custom);
            RemoteViews[] layouts = {n.bigContentView, n.contentView, n.headsUpContentView};
            String[] sources = {"expanded", "collapsed", "heads_up"};
            for (int i = 0; i < layouts.length; i++) {
                if (layouts[i] == null) continue;
                try {
                    Context owner = createPackageContext(sbn.getPackageName(), Context.CONTEXT_IGNORE_SECURITY);
                    View root = layouts[i].apply(owner, new FrameLayout(owner));
                    walk(root, sources[i], texts, views, viewProgress);
                } catch (Exception e) {
                    errors.put(sources[i] + ": " + e.getClass().getSimpleName() + ": " + e.getMessage());
                }
            }
            if (custom && texts.isEmpty() && errors.length() == 0) {
                errors.put("Custom views have no accessible text (possibly image-only content).");
            }
            out.put("view_text", new JSONArray(texts));
            out.put("views", views);
            out.put("view_progress", viewProgress);
            out.put("extraction_errors", errors);
        } catch (Exception e) {
            try { out.put("extraction_error", e.toString()); } catch (JSONException ignored) { }
        }
        return out;
    }

    private void walk(View view, String source, LinkedHashSet<String> texts,
                      JSONArray views, JSONArray progress) throws JSONException {
        if (view.getVisibility() != View.VISIBLE) return;
        String id = "";
        try { id = view.getResources().getResourceName(view.getId()); } catch (Exception ignored) { }
        CharSequence text = view instanceof TextView ? ((TextView) view).getText() : null;
        CharSequence description = view.getContentDescription();
        if ((text != null && text.length() > 0) || (description != null && description.length() > 0)) {
            JSONObject node = new JSONObject();
            node.put("source", source);
            node.put("resource_id", id);
            putText(node, "text", text);
            putText(node, "content_description", description);
            views.put(node);
            if (text != null && text.length() > 0) texts.add(text.toString());
            if (description != null && description.length() > 0) texts.add(description.toString());
        }
        if (view instanceof ProgressBar) {
            ProgressBar bar = (ProgressBar) view;
            JSONObject item = new JSONObject();
            item.put("source", source);
            item.put("resource_id", id);
            item.put("value", bar.getProgress());
            item.put("max", bar.getMax());
            item.put("indeterminate", bar.isIndeterminate());
            progress.put(item);
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) walk(group.getChildAt(i), source, texts, views, progress);
        }
    }
}
