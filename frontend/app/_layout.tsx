import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { LogBox, StyleSheet } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";
import { StatusBar } from "expo-status-bar";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider } from "@/src/auth-context";
import { CartProvider } from "@/src/cart-context";
import { colors } from "@/src/theme";

LogBox.ignoreAllLogs(true);

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <KeyboardProvider>
              <BottomSheetModalProvider>
                <AuthProvider>
                  <CartProvider>
                    <StatusBar style="dark" />
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
                    </Stack>
                  </CartProvider>
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
