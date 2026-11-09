import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { LogBox, Platform, StyleSheet } from "react-native";
import * as Notifications from "expo-notifications";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";
import { StatusBar } from "expo-status-bar";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider } from "@/src/auth-context";
import { CartProvider } from "@/src/cart-context";
import { StoreProvider } from "@/src/store-context";
import { AppChrome } from "@/src/components/app-chrome";
import { PushManager } from "@/src/components/push-manager";
import { LocationGate } from "@/src/components/location-gate";
import { colors } from "@/src/theme";

LogBox.ignoreAllLogs(true);

// Push (native only): show notifications while the app is open, and the Android channel must exist before any push arrives
if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({ shouldShowAlert: true, shouldPlaySound: true, shouldSetBadge: false, shouldShowBanner: true, shouldShowList: true }),
  });
}
if (Platform.OS === "android") {
  Notifications.setNotificationChannelAsync("default", { name: "Default", importance: Notifications.AndroidImportance.MAX, sound: "default" });
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <KeyboardProvider>
              <BottomSheetModalProvider>
                <AuthProvider>
                  <StoreProvider>
                  <CartProvider>
                    <StatusBar style="dark" />
                    <LocationGate>
                    <AppChrome>
                    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
                      <Stack.Screen name="(tabs)" />
                      <Stack.Screen name="login" options={{ presentation: "modal" }} />
                      <Stack.Screen name="register" options={{ presentation: "modal" }} />
                      <Stack.Screen name="product/[id]" />
                      <Stack.Screen name="category/[id]" />
                      <Stack.Screen name="search" />
                      <Stack.Screen name="checkout" />
                      <Stack.Screen name="order/[id]" />
                      <Stack.Screen name="wishlist" />
                      <Stack.Screen name="orders" />
                      <Stack.Screen name="scan" />
                    </Stack>
                    <PushManager />
                    </AppChrome>
                    </LocationGate>
                  </CartProvider>
                  </StoreProvider>
                </AuthProvider>
              </BottomSheetModalProvider>
            </KeyboardProvider>
          </QueryClientProvider>
        </ErrorBoundary>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
